"""Mission stage-machine reconciler (spec sections 6, 24).

`cycle()` is the handler for the `mission.cycle` task: a self-rescheduling
tick that waits for the current batch of literature/experiment work to
drain, then runs contradiction resolution, confidence assessment and the
Termination Engine, and either starts another research iteration or moves
the mission into criticism -> verdict -> report.

This is the one place that decides when a mission is "done enough" --
everything else (handlers, tools, evidence) only ever adds data.
"""

from __future__ import annotations

import uuid
from typing import List, Tuple

from .domain import Outcome, Phase, TERMINAL_STATUSES, profile
from .events import emit
from .evidence import confidence as confidence_mod
from .evidence import contradiction as contradiction_mod
from . import mission as mission_mod
from . import termination as termination_mod
from .orchestration.engine import PgWorkflowEngine, TaskSpec
from .storage.db import J

SATURATION_WINDOW = "last_cycle"


CYCLE_DELAY_S = 10.0


def _new_cycle_spec(priority: int = 1, delay_s: float = CYCLE_DELAY_S) -> TaskSpec:
    return TaskSpec("mission.cycle", "research", {}, priority=priority,
                    dedupe_key=f"mission.cycle:{uuid.uuid4().hex[:12]}",
                    delay_s=delay_s, counts_toward_budget=False)


def _elapsed_s(conn, mid: str) -> float:
    row = conn.execute(
        "SELECT EXTRACT(EPOCH FROM (now() - COALESCE(started_at, created_at))) AS s FROM missions WHERE id=%s",
        (mid,)).fetchone()
    return float(row["s"]) if row else 0.0


def _tasks_used(conn, mid: str) -> int:
    row = conn.execute("SELECT COALESCE(tasks_used,0) AS n FROM budgets WHERE mission_id=%s", (mid,)).fetchone()
    return int(row["n"]) if row else 0


def _source_count(conn, mid: str) -> int:
    return conn.execute("SELECT count(*) AS n FROM sources WHERE mission_id=%s", (mid,)).fetchone()["n"]


def _physical_status(conn, mid: str, state: dict) -> Tuple[bool, bool]:
    required = bool(state.get("physical_only"))
    if not required:
        return False, False
    row = conn.execute(
        "SELECT 1 FROM approvals WHERE mission_id=%s AND kind='physical_experiment' AND status='APPROVED' LIMIT 1",
        (mid,)).fetchone()
    return True, row is not None


def cycle(ctx, task: dict) -> Tuple[dict, List[TaskSpec]]:
    mid = task["mission_id"]
    with ctx.db.tx() as c:
        m = c.execute("SELECT * FROM missions WHERE id=%s FOR UPDATE", (mid,)).fetchone()
        if m is None or m["status"] in TERMINAL_STATUSES or m["status"] == "WAITING_FOR_HUMAN":
            return {"skipped": True}, []
        outstanding = PgWorkflowEngine.outstanding(c, mid) - 1  # this task itself is LEASED

    if outstanding > 0:
        return {"outstanding": outstanding}, [_new_cycle_spec()]

    # batch drained: resolve contradictions, then assess + decide
    with ctx.db.tx() as c:
        contradiction_mod.detect(c, mid)
    contradiction_mod.resolve_all(ctx.db, ctx.router, mid, question=m["question"],
                                  allow_premium=not m["demo"])

    with ctx.db.tx() as c:
        state = mission_mod.load_state(c, mid)
        a = confidence_mod.assess(c, mid)
        confidence_mod.apply(c, mid, a)
        prof = profile(m["research_depth"])
        q = termination_mod.compute_rqs(c, mid, prof, a)
        elapsed = _elapsed_s(c, mid)
        tasks_used = _tasks_used(c, mid)
        sources_now = _source_count(c, mid)
        last_conf = float(state.get("last_confidence", 0.0))
        last_sources = int(state.get("last_sources", 0))
        is_sat = termination_mod.saturated(m["iteration"], sources_now - last_sources, abs(a.confidence - last_conf))
        phys_required, phys_approved = _physical_status(c, mid, state)
        decision = termination_mod.decide(
            prof=prof, iteration=m["iteration"], elapsed_s=elapsed, tasks_used=tasks_used,
            confidence=a.confidence, rqs=q.rqs, physical_required=phys_required,
            physical_approved=phys_approved, is_saturated=is_sat)
        state["last_confidence"] = a.confidence
        state["last_sources"] = sources_now
        mission_mod.save_state(c, mid, state, announce=False)
        c.execute("UPDATE missions SET rqs=%s, maturity=%s, updated_at=now() WHERE id=%s",
                 (q.rqs, min(1.0, (m["iteration"] + 1) / max(1, prof.max_iterations)), mid))
        emit(c, mid, "TERMINATION_CHECK", {"outcome": str(decision.outcome), "reasons": decision.reasons,
                                           "confidence": round(a.confidence, 4), "rqs": round(q.rqs, 4),
                                           "iteration": m["iteration"]})

    if decision.outcome == Outcome.BLOCKED_EXTERNAL_EXPERIMENT:
        with ctx.db.tx() as c:
            exists = c.execute(
                "SELECT 1 FROM approvals WHERE mission_id=%s AND kind='physical_experiment' AND status='PENDING'",
                (mid,)).fetchone()
            if not exists:
                c.execute("INSERT INTO approvals(mission_id, kind, request) VALUES (%s,'physical_experiment',%s)",
                         (mid, J({"reason": "mission plan requires a physical experiment"})))
                emit(c, mid, "APPROVAL_REQUESTED", {"kind": "physical_experiment"})
            c.execute("UPDATE missions SET status='WAITING_FOR_HUMAN', updated_at=now() WHERE id=%s", (mid,))
        return {"decision": str(decision.outcome)}, []

    if decision.outcome == Outcome.CONTINUE:
        next_iter = m["iteration"] + 1
        with ctx.db.tx() as c:
            c.execute("UPDATE missions SET iteration=%s, updated_at=now() WHERE id=%s", (next_iter, mid))
        spawn = []
        for i, qy in enumerate((state.get("queries") or [])[:prof.queries_per_cycle]):
            spawn.append(TaskSpec("lit.search", "literature", {"query": qy}, iteration=next_iter,
                                  dedupe_key=f"lit.search:{next_iter}:{i}"))
        spawn.append(_new_cycle_spec())
        return {"decision": "CONTINUE", "iteration": next_iter}, spawn

    # STOP_* -> criticism, then verdict, then report
    with ctx.db.tx() as c:
        c.execute("UPDATE missions SET status='VALIDATING', stop_reason=%s, updated_at=now() WHERE id=%s",
                 (str(decision.outcome), mid))
        mission_mod.set_phase(c, mid, Phase.CRITICISM)
    spawn = [TaskSpec("critic.review", "criticism", {"role": role}, iteration=m["iteration"],
                      dedupe_key=f"critic.review:{role}:{m['iteration']}")
             for role in prof.critics]
    spawn.append(TaskSpec("verdict.build", "verification", {}, iteration=m["iteration"],
                          dedupe_key=f"verdict.build:{m['iteration']}"))
    return {"decision": str(decision.outcome), "reasons": decision.reasons}, spawn
