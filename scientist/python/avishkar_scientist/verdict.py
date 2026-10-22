"""Verdict Engine (spec sections 25, 26, 38).

Separate from the research core: it reads a *finalized package* -- a
deterministic, canonical-JSON snapshot of everything the mission found --
hashes it (sha256), and decides a label from the numbers alone. Models
only ever add:

* a council opinion (DEEP/EXTREME): judge A Gemini, judge B OpenRouter,
  judge C local; the council may make the label MORE cautious, never bolder,
  and a judge that disagrees on direction turns the verdict CONTESTED;
* narrative text, which must pass `numeric_guard` (every number it states
  must exist in the package) or the deterministic narrative is used.

INSUFFICIENT_EVIDENCE / PHYSICAL_VALIDATION_REQUIRED / CONTESTED always
carry the exact integrity phrase (spec 38) as the statement.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from typing import Optional

from .domain import INTEGRITY_PHRASES, VerdictLabel
from .evidence.confidence import assess

ORDINAL = {"SUPPORTED": 2, "LIKELY_SUPPORTED": 1, "CONTESTED": 0, "INSUFFICIENT_EVIDENCE": 0,
           "LIKELY_NOT_SUPPORTED": -1, "NOT_SUPPORTED": -2}
VALID_LABELS = tuple(v.value for v in VerdictLabel)
REINVESTIGATE_SPREAD = 0.5          # judges two ordinal steps apart (or opposite directions)


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256(obj) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


# -- package -------------------------------------------------------------------
def build_package(conn, mid: str) -> dict:
    m = conn.execute("SELECT * FROM missions WHERE id=%s", (mid,)).fetchone()
    a = assess(conn, mid)
    hyps = conn.execute("SELECT label, statement, kind, status, round(probability::numeric,4) AS p "
                        "FROM hypotheses WHERE mission_id=%s ORDER BY label", (mid,)).fetchall()

    def contrib(c):
        return {"claim": c.claim_text[:400], "weight": c.weight, "origin": c.origin, "origin_id": c.origin_id,
                "label": c.label[:200], "quote": c.quote[:300]}

    contras = conn.execute(
        "SELECT x.id, x.severity, x.resolution, x.explanation, a.text AS a, b.text AS b FROM contradictions x "
        "JOIN claims a ON a.id=x.claim_a JOIN claims b ON b.id=x.claim_b WHERE x.mission_id=%s ORDER BY x.id",
        (mid,)).fetchall()
    exps = conn.execute(
        "SELECT id, kind, title, status, supports, reproducibility, support_criterion, result "
        "FROM experiments WHERE mission_id=%s ORDER BY id", (mid,)).fetchall()
    reps = conn.execute(
        "SELECT r.experiment_id, r.method, r.status, r.agreement, r.reproducibility FROM replications r "
        "JOIN experiments e ON e.id=r.experiment_id WHERE e.mission_id=%s ORDER BY r.id", (mid,)).fetchall()
    crit = conn.execute(
        "SELECT role, iteration, round(score::numeric,3) AS score, issues FROM critic_reports "
        "WHERE mission_id=%s ORDER BY iteration, role", (mid,)).fetchall()
    st = conn.execute("SELECT state FROM research_states WHERE mission_id=%s", (mid,)).fetchone()
    state = (st["state"] if st else {}) or {}
    checks = state.get("checks") or []
    nsrc = conn.execute("SELECT count(*) AS n, count(*) FILTER (WHERE analyzed) AS a, "
                        "count(*) FILTER (WHERE demo_simulated) AS d FROM sources WHERE mission_id=%s",
                        (mid,)).fetchone()
    return {
        "mission_id": mid, "question": m["question"], "depth": m["research_depth"], "demo": bool(m["demo"]),
        "iteration": m["iteration"], "stop_reason": m["stop_reason"],
        "assessment": a.summary(),
        "rqs": float(m["rqs"]) if m["rqs"] is not None else None,
        "hypotheses": [dict(h, p=float(h["p"])) for h in hyps],
        "supporting": [contrib(c) for c in a.top(+1, 5)],
        "refuting": [contrib(c) for c in a.top(-1, 5)],
        "contradictions": [dict(c) for c in contras],
        "experiments": [dict(e) for e in exps],
        "replications": [dict(r) for r in reps],
        "critics": [dict(c) for c in crit],
        "termination": checks[-1] if checks else None,
        "sources": {"found": nsrc["n"], "analyzed": nsrc["a"], "simulated": nsrc["d"]},
        "physical_required": any(e["status"] == "PHYSICAL_EXPERIMENT_REQUIRED" for e in exps),
    }


# -- label ---------------------------------------------------------------------
def decide_label(pkg: dict, evidence_threshold: float) -> str:
    a = pkg["assessment"]
    p, conf, n = a["p_support"], a["confidence"], a["n_eff"]
    if pkg.get("physical_required") and n < 1.5:
        return str(VerdictLabel.PHYSICAL_VALIDATION_REQUIRED)
    if n < 0.5:
        return str(VerdictLabel.INSUFFICIENT_EVIDENCE)
    high_open = any(c["severity"] == "HIGH" and c["resolution"] in ("UNRESOLVED", "DOCUMENTED")
                    for c in pkg["contradictions"])
    if high_open and 0.4 <= p <= 0.6:
        return str(VerdictLabel.CONTESTED)
    pos = p >= 0.5
    strong, weak = ("SUPPORTED", "LIKELY_SUPPORTED") if pos else ("NOT_SUPPORTED", "LIKELY_NOT_SUPPORTED")
    if conf >= evidence_threshold:
        return strong
    if conf >= 0.3:
        return weak
    if abs(p - 0.5) < 0.1 and n >= 1.5:
        return str(VerdictLabel.CONTESTED)
    return str(VerdictLabel.INSUFFICIENT_EVIDENCE)


def apply_caution(base: str, council: Optional[str]) -> str:
    """The council can only make a verdict more cautious (spec 26)."""
    if not council or council not in ORDINAL or base == VerdictLabel.PHYSICAL_VALIDATION_REQUIRED:
        return base
    if base not in ORDINAL:
        return base
    b, c = ORDINAL[base], ORDINAL[council]
    if b * c < 0:
        return str(VerdictLabel.CONTESTED)
    if abs(c) < abs(b) and (c == 0 or (c > 0) == (b > 0)):
        return council
    return base


# -- council -------------------------------------------------------------------
JUDGE_SYSTEM = (
    "You are an independent scientific judge on a review council. Using ONLY the evidence package given, "
    "decide the verdict on the primary hypothesis H1. label must be one of: SUPPORTED, LIKELY_SUPPORTED, "
    "CONTESTED, LIKELY_NOT_SUPPORTED, NOT_SUPPORTED, INSUFFICIENT_EVIDENCE. Be conservative: weak or "
    "unreplicated evidence never earns SUPPORTED. Never invent papers, data or numbers. "
    'Schema: {"label": "", "confidence": 0.0, "rationale": "three sentences max"}'
)


def _package_brief(pkg: dict) -> str:
    brief = {k: pkg[k] for k in ("question", "assessment", "rqs", "hypotheses", "supporting", "refuting",
                                 "experiments", "replications", "stop_reason")}
    brief["contradictions"] = [{k: c[k] for k in ("severity", "resolution", "a", "b")} for c in pkg["contradictions"]]
    brief["critic_issues"] = [i for c in pkg["critics"] for i in (c.get("issues") or [])][:12]
    return canonical(brief)[:9000]


@dataclasses.dataclass
class Council:
    judges: dict
    label: Optional[str]
    spread: float

    def as_dict(self) -> dict:
        return {"judges": self.judges, "label": self.label, "spread": round(self.spread, 3)}


def run_council(router, pkg: dict, *, mid: str, task_id: Optional[int]) -> Council:
    from .models.router import ModelUnavailable
    judges = {}
    brief = _package_brief(pkg)
    for name, purpose in (("A", "council_judge_a"), ("B", "council_judge_b"), ("C", "council_judge_c")):
        try:
            data, res = router.complete_json(purpose, JUDGE_SYSTEM, brief, mission_id=mid, task_id=task_id,
                                             max_tokens=500)
        except ModelUnavailable as exc:
            judges[name] = {"status": "unavailable", "note": str(exc)[:200]}
            continue
        if not isinstance(data, dict) or str(data.get("label", "")).upper() not in ORDINAL:
            judges[name] = {"status": "invalid", "model": f"{res.provider}:{res.model}"}
            continue
        try:
            conf = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
        except (TypeError, ValueError):
            conf = 0.5
        judges[name] = {"status": "ok", "label": str(data["label"]).upper(), "confidence": conf,
                        "rationale": str(data.get("rationale") or "")[:600], "model": f"{res.provider}:{res.model}"}
    ok = [j for j in judges.values() if j.get("status") == "ok"]
    if not ok:
        return Council(judges, None, 0.0)
    ords = [ORDINAL[j["label"]] for j in ok]
    spread = (max(ords) - min(ords)) / 4.0
    # synthesizer: confidence-weighted mean ordinal, rounded toward zero (caution)
    wsum = sum(j["confidence"] for j in ok) or 1.0
    mean = sum(ORDINAL[j["label"]] * j["confidence"] for j in ok) / wsum
    o = int(mean) if mean >= 0 else -int(-mean)
    if min(ords) < 0 < max(ords):
        synth = "CONTESTED"
    else:
        synth = {2: "SUPPORTED", 1: "LIKELY_SUPPORTED", 0: "CONTESTED" if len({*ords}) > 1 else ok[0]["label"],
                 -1: "LIKELY_NOT_SUPPORTED", -2: "NOT_SUPPORTED"}[o]
    return Council(judges, synth, spread)


# -- narrative -------------------------------------------------------------------
_NUM = re.compile(r"(?<![A-Za-z0-9_.])-?\d+(?:\.\d+)?")


def _numbers_in(obj) -> set:
    out = set()
    for tok in _NUM.findall(canonical(obj)):
        try:
            v = float(tok)
        except ValueError:
            continue
        for x in (v, v * 100):
            out.add(round(x))
            out.add(round(x, 1))
            out.add(round(x, 2))
    return out


def numeric_guard(text: str, pkg: dict) -> bool:
    """True when every number in `text` exists in the package (or is a small count)."""
    allowed = _numbers_in(pkg)
    for tok in _NUM.findall(text or ""):
        v = float(tok)
        if v.is_integer() and 0 <= v <= 10:
            continue
        if not any(round(v, d) in allowed for d in (0, 1, 2)):
            return False
    return True


def deterministic_narrative(pkg: dict, label: str) -> str:
    a = pkg["assessment"]
    lines = [f"Verdict: {label.replace('_', ' ').lower()}."]
    if label in INTEGRITY_PHRASES:
        lines.insert(0, INTEGRITY_PHRASES[label])
    lines.append(f"The evidence gives H1 a support probability of {a['p_support']:.2f} with confidence "
                 f"{a['confidence']:.2f}, from an effective evidence mass of {a['n_eff']:.2f} across "
                 f"{a['independence'].get('independent_groups', 0)} independent source groups "
                 f"(evidence strength {a['evidence_strength']}).")
    if pkg["refuting"]:
        lines.append(f"Strongest evidence against H1: \"{pkg['refuting'][0]['claim'][:200]}\" ({pkg['refuting'][0]['label'][:120]}).")
    if pkg["supporting"]:
        lines.append(f"Strongest evidence for H1: \"{pkg['supporting'][0]['claim'][:200]}\" ({pkg['supporting'][0]['label'][:120]}).")
    open_c = [c for c in pkg["contradictions"] if c["resolution"] in ("UNRESOLVED", "DOCUMENTED")]
    if open_c:
        lines.append(f"{len(open_c)} contradiction(s) remain open and lower confidence.")
    if pkg["stop_reason"]:
        lines.append(f"Research stopped with {pkg['stop_reason']}.")
    if pkg.get("demo"):
        lines.append("DEMO: every source in this mission is simulated; this verdict says nothing about the real world.")
    return " ".join(lines)


NARRATIVE_SYSTEM = (
    "You write the executive verdict paragraph of a scientific research report. Use ONLY the facts in the "
    "package and the decided label; do not change the label, do not add papers, data or numbers that are not "
    "in the package, and state uncertainty plainly. 4-6 sentences, plain prose."
)


def narrative(router, pkg: dict, label: str, *, mid: str, task_id: Optional[int], final: bool) -> tuple:
    """-> (text, source) where source is the model id or 'deterministic'."""
    from .models.router import ModelUnavailable
    det = deterministic_narrative(pkg, label)
    if router is None or not router.premium_available or pkg.get("demo"):
        return det, "deterministic"
    purpose = "final_verdict" if final else "verdict_narrative"
    try:
        res = router.complete(purpose, NARRATIVE_SYSTEM, f"LABEL: {label}\nPACKAGE: {_package_brief(pkg)}",
                              mission_id=mid, task_id=task_id, max_tokens=600)
    except ModelUnavailable:
        return det, "deterministic"
    text = (res.content or "").strip()
    if not text or not numeric_guard(text, pkg):
        return det, "deterministic (model narrative rejected by numeric guard)"
    if label in INTEGRITY_PHRASES and INTEGRITY_PHRASES[label] not in text:
        text = INTEGRITY_PHRASES[label] + " " + text
    return text, f"{res.provider}:{res.model}"


def statement(label: str, pkg: dict) -> str:
    if label in INTEGRITY_PHRASES:
        return INTEGRITY_PHRASES[label]
    h1 = next((h["statement"] for h in pkg["hypotheses"] if h["label"] == "H1"), pkg["question"])
    return {
        "SUPPORTED": f"The evidence supports: {h1}",
        "LIKELY_SUPPORTED": f"The evidence leans toward: {h1}",
        "LIKELY_NOT_SUPPORTED": f"The evidence leans against: {h1}",
        "NOT_SUPPORTED": f"The evidence does not support: {h1}",
    }.get(label, label)
