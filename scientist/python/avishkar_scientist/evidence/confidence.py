"""Confidence model (spec sections 17, 18, 40-41).

Deterministic and fully explainable, so the report can show *why*:

* direction toward H1 = claim stance (toward H1) x evidence stance (toward claim)
* weight = strength x source quality x epistemic multiplier
  (FACT/OBSERVATION 1.0, INFERENCE 0.8, HYPOTHESIS 0.5, SPECULATION 0.3);
  experiment evidence = strength x reproducibility (0.6 until replicated)
* independence: per (independence group, direction) only the MAX weight counts
* S, R = summed support / refute mass;  p(H1) = (S+1)/(S+R+2)  (Laplace prior)
* confidence = max(p, 1-p) x (1 - exp(-n/2)), n = S+R  (little evidence -> low
  confidence even when it all points one way)
* each HIGH unresolved/documented contradiction x0.85, MEDIUM x0.95 (max 3)
"""

from __future__ import annotations

import dataclasses
import math
from collections import defaultdict
from typing import List

from ..events import emit
from .independence import group_sources, summarize

EPISTEMIC_MULT = {"FACT": 1.0, "OBSERVATION": 1.0, "INFERENCE": 0.8, "HYPOTHESIS": 0.5, "SPECULATION": 0.3}
DEFAULT_REPRO = 0.6
CONTRA_PENALTY = {"HIGH": 0.85, "MEDIUM": 0.95}
PENALIZED_RESOLUTIONS = ("UNRESOLVED", "DOCUMENTED")

_EVIDENCE_SQL = """
SELECT e.id, e.claim_id, e.stance AS ev_stance, e.strength, e.epistemic, e.source_id, e.experiment_run_id,
       e.quote, e.quote_verified, c.stance AS claim_stance, c.text AS claim_text,
       s.quality, s.title, s.authors, s.year, s.is_retracted, s.demo_simulated, s.doi, s.provider,
       r.experiment_id, x.reproducibility, x.title AS exp_title
  FROM evidence e
  JOIN claims c ON c.id = e.claim_id
  LEFT JOIN sources s ON s.id = e.source_id
  LEFT JOIN experiment_runs r ON r.id = e.experiment_run_id
  LEFT JOIN experiments x ON x.id = r.experiment_id
 WHERE e.mission_id = %s
"""


def _sign(stance: str) -> int:
    return 1 if stance == "SUPPORTS" else -1 if stance == "REFUTES" else 0


def strength_label(n: float) -> str:
    if n <= 0.05:
        return "NONE"
    if n < 1.5:
        return "WEAK"
    if n < 4.0:
        return "MODERATE"
    return "STRONG"


@dataclasses.dataclass
class Contribution:
    evidence_id: int
    claim_id: int
    claim_text: str
    direction: int          # +1 supports H1, -1 refutes H1
    weight: float
    group: str
    origin: str             # "source" | "experiment"
    origin_id: int
    label: str              # human title of the origin
    quote: str
    counted: bool           # False when a stronger item from the same group already counted


@dataclasses.dataclass
class Assessment:
    p_support: float
    confidence: float
    raw_confidence: float
    n_eff: float
    support_mass: float
    refute_mass: float
    strength: str
    independence: dict
    contradiction_penalty: float
    contributions: List[Contribution]
    claim_status: dict      # claim_id -> (status, confidence)

    def top(self, direction: int, k: int = 5) -> List[Contribution]:
        xs = [c for c in self.contributions if c.direction == direction and c.counted]
        return sorted(xs, key=lambda c: -c.weight)[:k]

    def summary(self) -> dict:
        return {"p_support": round(self.p_support, 4), "confidence": round(self.confidence, 4),
                "raw_confidence": round(self.raw_confidence, 4), "n_eff": round(self.n_eff, 4),
                "support_mass": round(self.support_mass, 4), "refute_mass": round(self.refute_mass, 4),
                "evidence_strength": self.strength, "independence": self.independence,
                "contradiction_penalty": round(self.contradiction_penalty, 4)}


def assess(conn, mission_id: str) -> Assessment:
    rows = conn.execute(_EVIDENCE_SQL, (mission_id,)).fetchall()
    src_rows = {}
    for r in rows:
        if r["source_id"] is not None:
            src_rows[r["source_id"]] = {"id": r["source_id"], "title": r["title"], "authors": r["authors"]}
    groups = group_sources(list(src_rows.values()))

    contribs = []
    for r in rows:
        direction = _sign(r["claim_stance"]) * _sign(r["ev_stance"])
        if direction == 0:
            continue
        if r["source_id"] is not None:
            q = 0.05 if r["is_retracted"] else float(r["quality"] or 0.5)
            w = float(r["strength"]) * q * EPISTEMIC_MULT.get(r["epistemic"], 0.8)
            grp, origin, oid = groups[r["source_id"]], "source", r["source_id"]
            label = r["title"]
        else:
            repro = r["reproducibility"] if r["reproducibility"] is not None else DEFAULT_REPRO
            w = float(r["strength"]) * float(repro)
            grp, origin, oid = f"exp:{r['experiment_id']}", "experiment", r["experiment_id"]
            label = r["exp_title"] or f"experiment {r['experiment_id']}"
        contribs.append(Contribution(r["id"], r["claim_id"], r["claim_text"], direction, round(w, 4), grp,
                                     origin, oid, label or "", r["quote"] or "", False))

    best = {}
    for c in contribs:
        k = (c.group, c.direction)
        if k not in best or c.weight > best[k].weight:
            best[k] = c
    for c in best.values():
        c.counted = True
    S = sum(c.weight for c in best.values() if c.direction > 0)
    R = sum(c.weight for c in best.values() if c.direction < 0)
    p = (S + 1.0) / (S + R + 2.0)
    n = S + R
    raw = max(p, 1 - p) * (1 - math.exp(-n / 2.0))

    pen_rows = conn.execute(
        "SELECT severity FROM contradictions WHERE mission_id=%s AND resolution = ANY(%s) "
        "AND severity IN ('HIGH','MEDIUM') ORDER BY severity='HIGH' DESC LIMIT 3",
        (mission_id, list(PENALIZED_RESOLUTIONS))).fetchall()
    penalty = 1.0
    for pr in pen_rows:
        penalty *= CONTRA_PENALTY[pr["severity"]]

    # per-claim status: evidence stance is toward the claim itself
    per = defaultdict(lambda: [0.0, 0.0])
    weight_of = {c.evidence_id: c.weight for c in contribs}
    claim_rows = conn.execute("SELECT id, stance FROM claims WHERE mission_id=%s", (mission_id,)).fetchall()
    for r in rows:
        s = _sign(r["ev_stance"])
        w = weight_of.get(r["id"], 0.0)
        if s > 0:
            per[r["claim_id"]][0] += w
        elif s < 0:
            per[r["claim_id"]][1] += w
    contested = {x["c"] for x in conn.execute(
        "SELECT claim_a AS c FROM contradictions WHERE mission_id=%s AND resolution = ANY(%s) "
        "UNION SELECT claim_b FROM contradictions WHERE mission_id=%s AND resolution = ANY(%s)",
        (mission_id, list(PENALIZED_RESOLUTIONS), mission_id, list(PENALIZED_RESOLUTIONS))).fetchall()}
    status = {}
    for cr in claim_rows:
        sup, ref = per.get(cr["id"], (0.0, 0.0))
        if sup == 0 and ref == 0:
            st, cf = "UNVERIFIED", 0.0
        elif cr["id"] in contested or (sup > 0 and ref > 0):
            st, cf = "CONTESTED", sup / (sup + ref)
        elif sup > 0:
            st, cf = "SUPPORTED", min(1.0, sup)
        else:
            st, cf = "REFUTED", min(1.0, ref)
        status[cr["id"]] = (st, round(cf, 4))

    return Assessment(p, raw * penalty, raw, n, S, R, strength_label(n), summarize(groups) if groups else
                      {"sources": 0, "independent_groups": 0, "merged": 0}, penalty, contribs, status)


def apply(conn, mission_id: str, a: Assessment) -> None:
    """Persist claim statuses, hypothesis probabilities and mission confidence."""
    for cid, (st, cf) in a.claim_status.items():
        conn.execute("UPDATE claims SET status=%s, confidence=%s WHERE id=%s AND (status<>%s OR confidence<>%s)",
                     (st, cf, cid, st, cf))
    h = conn.execute("SELECT id, label, probability FROM hypotheses WHERE mission_id=%s AND label IN ('H1','H0')",
                     (mission_id,)).fetchall()
    for row in h:
        prob = a.p_support if row["label"] == "H1" else 1 - a.p_support
        if a.n_eff <= 0.05:
            st = "OPEN"
        elif a.confidence >= 0.3:
            st = "SUPPORTED" if prob > 0.5 else "REFUTED"
        else:
            st = "UNRESOLVED"
        if abs(float(row["probability"]) - prob) >= 0.005:
            conn.execute("UPDATE hypotheses SET probability=%s, status=%s, updated_at=now() WHERE id=%s",
                         (prob, st, row["id"]))
            emit(conn, mission_id, "HYPOTHESIS_UPDATED", {"label": row["label"], "probability": round(prob, 4),
                                                          "status": st})
    conn.execute("UPDATE missions SET confidence=%s, evidence_strength=%s, updated_at=now() WHERE id=%s",
                 (a.confidence, a.strength, mission_id))
