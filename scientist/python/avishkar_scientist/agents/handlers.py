"""Task handlers (spec sections 14-23).

Every handler has the signature `(ctx, task) -> (output: dict, spawn: list[TaskSpec])`.
The worker loop (orchestration/worker.py) leases a task, calls the handler,
and passes `spawn` straight to `engine.complete(..., spawn=spawn)`, which
enqueues the follow-on tasks in the same transaction that marks this task
SUCCEEDED. Handlers never call `engine.enqueue` themselves.

Demo missions (`task["demo"]`... actually the mission row's `demo` flag)
never make a model or network call: every handler below branches on it
early and uses the fixed `tools.mock` fixtures instead.
"""

from __future__ import annotations

import dataclasses
import time
from typing import List, Tuple

from .. import core
from ..domain import Phase
from ..events import emit
from ..evidence import extract as extract_mod
from ..evidence import store
from ..models.router import ModelUnavailable
from ..orchestration.engine import TaskSpec
from ..storage.db import J
from ..tools import SEARCH_TOOLS
from ..tools.literature import providers_for
from ..tools.mock import DEMO_EXPERIMENT, DEMO_PLAN
from ..tools.registry import ToolDenied, ToolError
from ..tools.sandbox import eval_criterion
from . import critics as critics_mod

Output = Tuple[dict, List[TaskSpec]]

PLAN_SYSTEM = (
    "You are a research scientist scoping a question before investigating it. Given the QUESTION, propose: "
    "h1 (the primary testable hypothesis, one sentence), h0 (its null/negation, one sentence), "
    "alternatives (0-2 other explanations worth tracking), queries (3-6 short literature search queries), "
    "physical_only (true only if the hypothesis can ONLY be tested with a real-world physical experiment, "
    "never with literature or computation), experiment_idea (one sentence describing a computational or "
    "statistical check that could be run, or empty string if none applies). "
    'Schema: {"h1":"","h0":"","alternatives":[],"queries":[],"physical_only":false,"experiment_idea":""}'
)


def _mission(conn, mid: str) -> dict:
    return conn.execute("SELECT * FROM missions WHERE id=%s", (mid,)).fetchone()


# -- plan.scope ---------------------------------------------------------------
def h_plan_scope(ctx, task: dict) -> Output:
    mid = task["mission_id"]
    question = task["input"]["question"]
    with ctx.db.tx() as c:
        m = _mission(c, mid)
        c.execute("UPDATE missions SET status='RUNNING', started_at=COALESCE(started_at, now()), "
                 "updated_at=now() WHERE id=%s", (mid,))

    if m["demo"]:
        plan = dict(DEMO_PLAN)
    else:
        plan = None
        try:
            data, _res = ctx.router.complete_json("plan_generation", PLAN_SYSTEM, f"QUESTION: {question}",
                                                  mission_id=mid, task_id=task["id"], max_tokens=700)
            if isinstance(data, dict) and data.get("h1") and data.get("h0"):
                plan = {
                    "h1": str(data["h1"])[:1000], "h0": str(data["h0"])[:1000],
                    "alternatives": [str(x)[:500] for x in (data.get("alternatives") or [])][:2],
                    "queries": [str(x)[:300] for x in (data.get("queries") or [])][:6] or [question[:300]],
                    "physical_only": bool(data.get("physical_only")),
                    "experiment_idea": str(data.get("experiment_idea") or "")[:500],
                }
        except ModelUnavailable:
            plan = None
        if plan is None:
            plan = {"h1": question, "h0": f"It is not the case that: {question}", "alternatives": [],
                   "queries": [question[:300]], "physical_only": False, "experiment_idea": ""}

    with ctx.db.tx() as c:
        h1 = store.upsert_hypothesis(c, mid, "H1", plan["h1"], "primary")
        store.upsert_hypothesis(c, mid, "H0", plan["h0"], "null")
        for i, alt in enumerate(plan["alternatives"]):
            store.upsert_hypothesis(c, mid, f"H{2 + i}", alt, "alternative")
        state = {"queries": plan["queries"], "physical_only": plan["physical_only"],
                 "experiment_idea": plan["experiment_idea"], "h1_id": h1}
        from .. import mission as mission_mod
        mission_mod.save_state(c, mid, state)
        mission_mod.set_phase(c, mid, Phase.LITERATURE_RESEARCH)

    spawn = [TaskSpec("lit.search", "literature", {"query": q}, dedupe_key=f"lit.search:0:{i}")
             for i, q in enumerate(plan["queries"])]
    prof = _profile(m)
    if prof.max_experiments > 0 and not plan["physical_only"]:
        spawn.append(TaskSpec("experiment.run", "experiment", {"idea": plan["experiment_idea"]},
                              dedupe_key="experiment.run:main"))
    spawn.append(TaskSpec("mission.cycle", "research", {}, priority=1, dedupe_key="mission.cycle:seed",
                          delay_s=core.CYCLE_DELAY_S, counts_toward_budget=False))
    return {"h1": plan["h1"], "queries": plan["queries"]}, spawn


def _profile(m: dict):
    from ..domain import profile
    return profile(m["research_depth"])


# -- lit.search -----------------------------------------------------------------
def h_lit_search(ctx, task: dict) -> Output:
    mid, query = task["mission_id"], task["input"]["query"]
    with ctx.db.tx() as c:
        m = _mission(c, mid)
        have = c.execute("SELECT count(*) AS n FROM sources WHERE mission_id=%s", (mid,)).fetchone()["n"]
    room = _profile(m).max_sources - have
    if room <= 0:
        return {"query": query, "found": 0, "skipped": "max_sources reached"}, []
    providers = ["demo"] if m["demo"] else list(providers_for(m["question"]))
    per_provider = []
    for name in providers:
        tool = SEARCH_TOOLS.get(name)
        if not tool:
            continue
        try:
            recs = ctx.registry.call(tool, task_type="lit.search", db=ctx.db, mission_id=mid,
                                     task_id=task["id"], query=query, limit=8)
        except (ToolDenied, ToolError):
            continue
        per_provider.append(list(recs or []))
    # round-robin across providers so one prolific provider can't take the whole source budget
    width = max((len(p) for p in per_provider), default=0)
    found = [r for tier in zip(*[p + [None] * (width - len(p)) for p in per_provider]) for r in tier if r]
    spawn, added = [], 0
    with ctx.db.tx() as c:
        for rec in found:
            if added >= room:
                break
            sid, new = store.upsert_source(c, ctx.objects, mid, rec, query=query)
            if not new:
                continue
            added += 1
            spawn.append(TaskSpec("source.analyze", "literature", {"source_id": sid},
                                  iteration=task["iteration"], dedupe_key=f"source.analyze:{sid}"))
    return {"query": query, "found": len(found), "added": added}, spawn


# -- source.analyze ---------------------------------------------------------------
def h_source_analyze(ctx, task: dict) -> Output:
    mid, sid = task["mission_id"], task["input"]["source_id"]
    with ctx.db.tx() as c:
        m = _mission(c, mid)
        src = c.execute("SELECT * FROM sources WHERE id=%s", (sid,)).fetchone()
        if src is None:
            return {"skipped": "source not found"}, []
        abstract = store.source_abstract(c, ctx.objects, sid)
        h1 = store.primary_hypothesis(c, mid)

    if m["demo"]:
        extraction = extract_mod.extract_demo(src["external_id"])
    else:
        extraction = extract_mod.extract_claims(
            ctx.router, question=m["question"], hypothesis=(h1["statement"] if h1 else m["question"]),
            title=src["title"], abstract=abstract, mission_id=mid, task_id=task["id"])

    with ctx.db.tx() as c:
        for ec in extraction.claims:
            cid, _new = store.upsert_claim(c, mid, ec.text, stance=ec.stance, epistemic=ec.epistemic,
                                           hypothesis_id=h1["id"] if h1 else None)
            store.add_evidence(c, mid, cid, stance="SUPPORTS", strength=ec.strength, epistemic=ec.epistemic,
                              source_id=sid, quote=ec.quote, quote_verified=ec.verified,
                              extractor=extraction.extractor)
        c.execute("UPDATE sources SET analyzed=true, relevance=%s WHERE id=%s", (extraction.relevance, sid))
    return {"claims": len(extraction.claims), "dropped": extraction.dropped}, []


# -- experiment.run ---------------------------------------------------------------
EXPERIMENT_SYSTEM = (
    "Write a short, self-contained Python program (stdlib + numpy/scipy/sympy/statsmodels only) that tests "
    "the given hypothesis computationally or statistically. It must print exactly one line starting with "
    "'RESULT_JSON: ' followed by a JSON object of the numeric result. No file or network access. "
    'Schema: {"title":"","rationale":"","support_criterion":"result[\\"x\\"] > 0","code":"..."}'
)


def _record_experiment_run(ctx, mid: str, task_id: int, hypothesis_id, design: dict, run, run_kind="primary",
                           seed: int = 0):
    import dataclasses as dc
    run_d = dc.asdict(run)
    with ctx.db.tx() as c:
        status = run.status if run.status != "COMPLETED" else "COMPLETED"
        supports = None
        if run.status == "COMPLETED" and design.get("support_criterion"):
            supports = eval_criterion(design["support_criterion"], run.result)
        row = c.execute(
            """INSERT INTO experiments(mission_id, hypothesis_id, kind, title, design, code, code_sha256,
                                       support_criterion, status, result, supports)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (mid, hypothesis_id, design.get("kind", "COMPUTATIONAL"), design["title"][:500], J(design),
             design.get("code"), ctx.objects.put(design.get("code") or ""), design.get("support_criterion"),
             status, J(run.result), supports)).fetchone()
        exp_id = row["id"]
        stdout_sha = ctx.objects.put(run.stdout or "")
        run_row = c.execute(
            """INSERT INTO experiment_runs(experiment_id, run_kind, seed, status, exit_code, duration_s,
                                           stdout_sha256, stderr_tail, result, sandbox)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (exp_id, run_kind, seed, run.status, run.exit_code, run.duration_s, stdout_sha, run.stderr_tail,
             J(run.result), J(run.sandbox))).fetchone()
        run_id = run_row["id"]
        c.execute("INSERT INTO budgets(mission_id, experiments_run) VALUES (%s,1) "
                 "ON CONFLICT (mission_id) DO UPDATE SET experiments_run=budgets.experiments_run+1, updated_at=now()",
                 (mid,))
        emit(c, mid, "EXPERIMENT_COMPLETED" if run.status == "COMPLETED" else "EXPERIMENT_STARTED",
             {"experiment_id": exp_id, "status": run.status, "title": design["title"][:200]})
        if run.status == "COMPLETED" and supports is not None and hypothesis_id:
            text = (f"Computational experiment '{design['title'][:200]}' "
                   f"{'supports' if supports else 'does not support'} H1.")
            cid, _new = store.upsert_claim(c, mid, text, stance="SUPPORTS" if supports else "REFUTES",
                                           epistemic="OBSERVATION", hypothesis_id=hypothesis_id)
            store.add_evidence(c, mid, cid, stance="SUPPORTS", strength=0.7, epistemic="OBSERVATION",
                              experiment_run_id=run_id, extractor="sandbox:deterministic")
    return exp_id, run_id, supports


def h_experiment_run(ctx, task: dict) -> Output:
    mid = task["mission_id"]
    with ctx.db.tx() as c:
        m = _mission(c, mid)
        h1 = store.primary_hypothesis(c, mid)
    h1_id = h1["id"] if h1 else None

    if m["demo"]:
        design = dict(DEMO_EXPERIMENT)
    else:
        idea = task["input"].get("idea") or m["question"]
        design = None
        try:
            data, _res = ctx.router.complete_json("experiment_design", EXPERIMENT_SYSTEM,
                                                  f"HYPOTHESIS: {h1['statement'] if h1 else m['question']}\n"
                                                  f"IDEA: {idea}", mission_id=mid, task_id=task["id"],
                                                  max_tokens=1200)
            if isinstance(data, dict) and data.get("code"):
                design = {"kind": "COMPUTATIONAL", "title": str(data.get("title") or idea)[:500],
                         "rationale": str(data.get("rationale") or "")[:1000],
                         "support_criterion": str(data.get("support_criterion") or ""),
                         "code": str(data["code"])}
        except ModelUnavailable:
            design = None
        if design is None:
            return {"skipped": "no experiment design available"}, []

    run = ctx.registry.call("sandbox.python", task_type="experiment.run", db=ctx.db, mission_id=mid,
                            task_id=task["id"], code=design["code"], seed=0, run_timeout_s=60)
    exp_id, run_id, supports = _record_experiment_run(ctx, mid, task["id"], h1_id, design, run)

    spawn = []
    if run.status == "COMPLETED" and _profile(m).replicate:
        spawn.append(TaskSpec("replication.run", "replication", {"experiment_id": exp_id},
                              dedupe_key=f"replication.run:{exp_id}"))
    return {"experiment_id": exp_id, "status": run.status, "supports": supports}, spawn


# -- replication.run ---------------------------------------------------------------
def h_replication_run(ctx, task: dict) -> Output:
    mid, exp_id = task["mission_id"], task["input"]["experiment_id"]
    with ctx.db.tx() as c:
        exp = c.execute("SELECT * FROM experiments WHERE id=%s", (exp_id,)).fetchone()
        emit(c, mid, "REPLICATION_STARTED", {"experiment_id": exp_id})
    if exp is None or not exp["code"]:
        return {"skipped": "experiment or code not found"}, []

    seed = int(time.time()) % 100000
    run = ctx.registry.call("sandbox.python", task_type="replication.run", db=ctx.db, mission_id=mid,
                            task_id=task["id"], code=exp["code"], seed=seed, run_timeout_s=60)
    new_supports = None
    if run.status == "COMPLETED" and exp["support_criterion"]:
        new_supports = eval_criterion(exp["support_criterion"], run.result)
    agreement = (new_supports == exp["supports"]) if (run.status == "COMPLETED" and exp["supports"] is not None) \
        else None
    reproducibility = 1.0 if agreement else (0.2 if agreement is False else None)

    with ctx.db.tx() as c:
        c.execute(
            """INSERT INTO experiment_runs(experiment_id, run_kind, seed, status, exit_code, duration_s,
                                           stdout_sha256, stderr_tail, result, sandbox)
               VALUES (%s,'replication_seed',%s,%s,%s,%s,%s,%s,%s,%s)""",
            (exp_id, seed, run.status, run.exit_code, run.duration_s, ctx.objects.put(run.stdout or ""),
             run.stderr_tail, J(run.result), J(run.sandbox)))
        c.execute(
            "INSERT INTO replications(mission_id, experiment_id, method, status, agreement, reproducibility, details) "
            "VALUES (%s,%s,'reseed',%s,%s,%s,%s) ON CONFLICT (experiment_id, method) DO UPDATE SET "
            "status=EXCLUDED.status, agreement=EXCLUDED.agreement, reproducibility=EXCLUDED.reproducibility, "
            "details=EXCLUDED.details",
            (mid, exp_id, run.status, agreement, reproducibility, J({"seed": seed, "result": run.result})))
        if reproducibility is not None:
            c.execute("UPDATE experiments SET reproducibility=%s, updated_at=now() WHERE id=%s",
                     (reproducibility, exp_id))
        emit(c, mid, "REPLICATION_COMPLETED", {"experiment_id": exp_id, "agreement": agreement})
    return {"experiment_id": exp_id, "agreement": agreement, "reproducibility": reproducibility}, []


# -- critic.review ---------------------------------------------------------------
def h_critic_review(ctx, task: dict) -> Output:
    from .. import verdict as verdict_mod
    mid, role = task["mission_id"], task["input"]["role"]
    with ctx.db.tx() as c:
        pkg = verdict_mod.build_package(c, mid)
    brief = verdict_mod._package_brief(pkg)
    result = critics_mod.review(None if pkg.get("demo") else ctx.router, role, brief, pkg,
                                mission_id=mid, task_id=task["id"])
    with ctx.db.tx() as c:
        c.execute(
            """INSERT INTO critic_reports(mission_id, iteration, role, score, issues, open_questions, model)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (mission_id, iteration, role) DO UPDATE SET
                 score=EXCLUDED.score, issues=EXCLUDED.issues, open_questions=EXCLUDED.open_questions,
                 model=EXCLUDED.model""",
            (mid, task["iteration"], role, result["score"], J(result["issues"]), J(result["open_questions"]),
             result.get("model")))
        emit(c, mid, "CRITIQUE_COMPLETED", {"role": role, "score": result["score"]})
    return result, []


# -- verdict.build ---------------------------------------------------------------
def h_verdict_build(ctx, task: dict) -> Output:
    from .. import verdict as verdict_mod
    mid = task["mission_id"]
    with ctx.db.tx() as c:
        m = _mission(c, mid)
        emit(c, mid, "VERDICT_STARTED", {})
        pkg = verdict_mod.build_package(c, mid)

    label = verdict_mod.decide_label(pkg, m["evidence_threshold"])
    council = None
    prof = _profile(m)
    if prof.council and not m["demo"]:
        council = verdict_mod.run_council(ctx.router, pkg, mid=mid, task_id=task["id"])
        label = verdict_mod.apply_caution(label, council.label)
    router = None if m["demo"] else ctx.router
    narrative_text, narrative_source = verdict_mod.narrative(router, pkg, label, mid=mid, task_id=task["id"],
                                                             final=True)
    stmt = verdict_mod.statement(label, pkg)
    pkg_hash = verdict_mod.sha256(pkg)

    with ctx.db.tx() as c:
        c.execute(
            """INSERT INTO verdicts(mission_id, label, statement, confidence, evidence_strength, package_sha256,
                                    package, narrative, council, stop_reason)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (mid, label, stmt, pkg["assessment"]["confidence"], pkg["assessment"]["evidence_strength"], pkg_hash,
             J(pkg), narrative_text, J(council.as_dict() if council else None), pkg.get("stop_reason")))
        c.execute("UPDATE missions SET verdict_label=%s, current_phase='VERDICT', updated_at=now() WHERE id=%s",
                 (label, mid))
        emit(c, mid, "VERDICT_READY", {"label": label, "statement": stmt, "narrative_source": narrative_source})
    return {"label": label, "statement": stmt}, [
        TaskSpec("report.generate", "reporting", {"attempt": 0}, iteration=task["iteration"],
                dedupe_key=f"report.generate:{task['iteration']}")]


# -- report.generate ---------------------------------------------------------------
def h_report_generate(ctx, task: dict) -> Output:
    from .. import reports as reports_mod
    mid = task["mission_id"]
    with ctx.db.tx() as c:
        m = _mission(c, mid)
        prof = _profile(m)
        done = c.execute("SELECT count(DISTINCT role) AS n FROM critic_reports WHERE mission_id=%s AND iteration=%s",
                         (mid, task["iteration"])).fetchone()["n"]
    attempt = int(task["input"].get("attempt", 0))
    if done < len(prof.critics) and attempt < 5:
        return {"waiting_on_critics": len(prof.critics) - done}, [
            TaskSpec("report.generate", "reporting", {"attempt": attempt + 1}, iteration=task["iteration"],
                    dedupe_key=f"report.generate:{task['iteration']}:{attempt + 1}")]

    with ctx.db.tx() as c:
        body = reports_mod.build_report(c, mid)
        sha = ctx.objects.put(body)
        c.execute("INSERT INTO reports(mission_id, format, sha256, body) VALUES (%s,'markdown',%s,%s)",
                 (mid, sha, body))
        emit(c, mid, "REPORT_READY", {"sha256": sha, "length": len(body)})
        c.execute("UPDATE missions SET status='COMPLETED', current_phase='REPORTING', completed_at=now(), "
                 "updated_at=now() WHERE id=%s", (mid,))
        emit(c, mid, "MISSION_COMPLETED", {"verdict_label": m["verdict_label"], "stop_reason": m["stop_reason"]})
    return {"report_sha256": sha}, []


HANDLERS = {
    "plan.scope": h_plan_scope,
    "lit.search": h_lit_search,
    "source.analyze": h_source_analyze,
    "experiment.run": h_experiment_run,
    "replication.run": h_replication_run,
    "critic.review": h_critic_review,
    "verdict.build": h_verdict_build,
    "report.generate": h_report_generate,
    "mission.cycle": core.cycle,
}
