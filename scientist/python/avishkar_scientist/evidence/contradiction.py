"""Contradiction detection and resolution (spec section 18).

Detection is deterministic: two claims contradict when they point in
opposite directions toward H1 and talk about the same thing --
embedding cosine >= 0.6 when both have embeddings, otherwise a lexical
rule (token Jaccard >= 0.15 with at least two shared content words; every
claim already concerns the same hypothesis, so the bar is low by design).
Pairs are stored with claim_a < claim_b, so re-running is idempotent.

Severity comes from the best source behind each side: HIGH when both
sides have a source of quality >= 0.7 (or an experiment), MEDIUM when one
side does (>= 0.55), else LOW.

Resolution: HIGH contradictions ask the premium `contradiction_resolution`
purpose (spec D3: Gemini only for key decisions). The model may only pick a
resolution label and explain it; it cannot add evidence. Without a model,
or for MEDIUM/LOW, a deterministic rule decides: ONE_SIDE_WEAKER when one
side's evidence weight is >= 2x the other's, else DOCUMENTED (kept in the
report as an open conflict and penalised in confidence).

Model calls happen outside any transaction (the router opens its own).
"""

from __future__ import annotations

import dataclasses
from typing import List, Optional

from ..domain import Resolution
from ..events import emit
from ..models.embed import jaccard, tokens

COSINE_MIN = 0.6
JACCARD_MIN = 0.15
SHARED_MIN = 2
WEAKER_RATIO = 2.0
EXPERIMENT_QUALITY = 0.8

_CLAIM_SQL = """
SELECT c.id, c.text, c.stance, (c.embedding IS NOT NULL) AS has_emb,
       COALESCE(MAX(CASE WHEN e.source_id IS NOT NULL
                         THEN CASE WHEN s.is_retracted THEN 0.05 ELSE s.quality END
                         ELSE %s END), 0) AS best_quality,
       COALESCE(SUM(e.strength * COALESCE(CASE WHEN e.source_id IS NOT NULL THEN s.quality END, %s)), 0) AS weight
  FROM claims c
  LEFT JOIN evidence e ON e.claim_id = c.id
  LEFT JOIN sources s ON s.id = e.source_id
 WHERE c.mission_id = %s AND c.stance IN ('SUPPORTS','REFUTES')
 GROUP BY c.id
"""

RESOLVE_SYSTEM = (
    "You are a rigorous scientific referee. Two claims gathered for the same research question point in "
    "opposite directions. Using ONLY the claims and their evidence summaries given, decide how the conflict "
    "stands. resolution must be one of: RESOLVED_CONDITIONAL (both can be true under different conditions -- "
    "name them), ONE_SIDE_WEAKER (one side rests on clearly weaker evidence -- say which and why), "
    "DOCUMENTED (a genuine open conflict that the evidence cannot settle). Never invent data, papers or "
    'numbers. Schema: {"resolution": "", "weaker": "A|B|null", "explanation": "two sentences max"}'
)


@dataclasses.dataclass
class Pair:
    id: int
    claim_a: int
    claim_b: int
    text_a: str
    text_b: str
    weight_a: float
    weight_b: float
    severity: str


def _severity(qa: float, qb: float) -> str:
    if qa >= 0.7 and qb >= 0.7:
        return "HIGH"
    if max(qa, qb) >= 0.55:
        return "MEDIUM"
    return "LOW"


def detect(conn, mission_id: str) -> List[int]:
    """Find and store new contradictions. -> ids of newly created rows."""
    rows = conn.execute(_CLAIM_SQL, (EXPERIMENT_QUALITY, EXPERIMENT_QUALITY, mission_id)).fetchall()
    sup = [r for r in rows if r["stance"] == "SUPPORTS"]
    ref = [r for r in rows if r["stance"] == "REFUTES"]
    if not sup or not ref:
        return []
    cos = {}
    if any(r["has_emb"] for r in sup) and any(r["has_emb"] for r in ref):
        for x in conn.execute(
                """SELECT a.id AS a, b.id AS b, 1 - (a.embedding <=> b.embedding) AS sim
                     FROM claims a JOIN claims b ON a.mission_id = b.mission_id
                    WHERE a.mission_id = %s AND a.stance = 'SUPPORTS' AND b.stance = 'REFUTES'
                      AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL""", (mission_id,)).fetchall():
            cos[(x["a"], x["b"])] = float(x["sim"])
    created = []
    for a in sup:
        ta = tokens(a["text"])
        for b in ref:
            c = cos.get((a["id"], b["id"]))
            lex = jaccard(a["text"], b["text"])
            shared = len(ta & tokens(b["text"]))
            if not ((c is not None and c >= COSINE_MIN) or (lex >= JACCARD_MIN and shared >= SHARED_MIN)):
                continue
            sim = c if c is not None else lex
            lo, hi = sorted((a["id"], b["id"]))
            sev = _severity(float(a["best_quality"]), float(b["best_quality"]))
            row = conn.execute(
                """INSERT INTO contradictions(mission_id, claim_a, claim_b, similarity, severity)
                   VALUES (%s,%s,%s,%s,%s) ON CONFLICT (mission_id, claim_a, claim_b) DO NOTHING RETURNING id""",
                (mission_id, lo, hi, round(sim, 4), sev)).fetchone()
            if row:
                created.append(row["id"])
                emit(conn, mission_id, "CONTRADICTION_FOUND", {
                    "contradiction_id": row["id"], "claim_a": lo, "claim_b": hi, "severity": sev,
                    "similarity": round(sim, 4), "supporting": a["text"][:200], "refuting": b["text"][:200]})
    return created


def unresolved(conn, mission_id: str) -> List[Pair]:
    rows = conn.execute(_CLAIM_SQL, (EXPERIMENT_QUALITY, EXPERIMENT_QUALITY, mission_id)).fetchall()
    info = {r["id"]: r for r in rows}
    out = []
    for x in conn.execute("SELECT id, claim_a, claim_b, severity FROM contradictions "
                          "WHERE mission_id=%s AND resolution='UNRESOLVED' ORDER BY id", (mission_id,)).fetchall():
        a, b = info.get(x["claim_a"]), info.get(x["claim_b"])
        if a is None or b is None:
            continue
        out.append(Pair(x["id"], x["claim_a"], x["claim_b"], a["text"], b["text"],
                        float(a["weight"]), float(b["weight"]), x["severity"]))
    return out


def deterministic(p: Pair) -> tuple:
    hi, lo = max(p.weight_a, p.weight_b), min(p.weight_a, p.weight_b)
    if hi > 0 and (lo == 0 or hi / lo >= WEAKER_RATIO):
        weaker = p.text_a if p.weight_a < p.weight_b else p.text_b
        return (str(Resolution.ONE_SIDE_WEAKER),
                f"Evidence weight {hi:.2f} vs {lo:.2f}; the weaker side is: \"{weaker[:160]}\".")
    return (str(Resolution.DOCUMENTED),
            f"Comparable evidence on both sides (weights {p.weight_a:.2f} vs {p.weight_b:.2f}); conflict left open.")


def resolve_with_model(router, p: Pair, *, question: str, mission_id: str, task_id: Optional[int]) -> Optional[tuple]:
    """Premium referee for one HIGH pair. -> (resolution, explanation, model) or None."""
    from ..models.router import ModelUnavailable
    user = (f"QUESTION: {question}\nCLAIM A (supports the hypothesis; evidence weight {p.weight_a:.2f}): {p.text_a}\n"
            f"CLAIM B (refutes the hypothesis; evidence weight {p.weight_b:.2f}): {p.text_b}")
    try:
        data, res = router.complete_json("contradiction_resolution", RESOLVE_SYSTEM, user,
                                         mission_id=mission_id, task_id=task_id, max_tokens=400)
    except ModelUnavailable:
        return None
    if not isinstance(data, dict):
        return None
    label = str(data.get("resolution") or "").strip().upper()
    if label not in (Resolution.RESOLVED_CONDITIONAL, Resolution.ONE_SIDE_WEAKER, Resolution.DOCUMENTED):
        return None
    expl = str(data.get("explanation") or "").strip()[:600] or "(no explanation given)"
    return str(label), expl, f"{res.provider}:{res.model}"


def store_resolution(conn, mission_id: str, pair_id: int, resolution: str, explanation: str, by: str) -> None:
    conn.execute("UPDATE contradictions SET resolution=%s, explanation=%s, resolved_by=%s, updated_at=now() "
                 "WHERE id=%s AND mission_id=%s AND resolution='UNRESOLVED'",
                 (resolution, explanation, by, pair_id, mission_id))


def resolve_all(db, router, mission_id: str, *, question: str, task_id: Optional[int] = None,
                allow_premium: bool = True) -> dict:
    """Resolve every UNRESOLVED pair. HIGH ones try the premium referee first."""
    with db.tx() as c:
        pairs = unresolved(c, mission_id)
    done = {"model": 0, "deterministic": 0}
    for p in pairs:
        out = None
        if allow_premium and p.severity == "HIGH" and router is not None and router.premium_available:
            out = resolve_with_model(router, p, question=question, mission_id=mission_id, task_id=task_id)
        if out:
            label, expl, by = out
            done["model"] += 1
        else:
            label, expl = deterministic(p)
            by = "deterministic"
            done["deterministic"] += 1
        with db.tx() as c:
            store_resolution(c, mission_id, p.id, label, expl, by)
    return done
