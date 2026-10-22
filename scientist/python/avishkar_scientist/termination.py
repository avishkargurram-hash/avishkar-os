"""Termination Engine (spec sections 24, 40, 42).

Deterministic: given the assessment, research quality and budgets it
returns one of the six outcomes with the reasons, so the report can say
exactly why a mission stopped. A premium `evidence_sufficiency` check may
only *downgrade* STOP_CONFIDENT to CONTINUE (handlers.py) -- a model can
never make the engine stop earlier than the evidence allows.

RQS (research quality score, spec 40) -- weights sum to 1:
  .20 independent groups / min(max_sources, 8)
  .15 verified-evidence fraction
  .20 1 - exp(-n_eff/3)
  .10 resolved-contradiction fraction (1.0 when there are none)
  .15 mean critic score of the latest round
  .10 experiments completed and replicated (neutral 0.5 when none allowed)
  .10 distinct literature providers / 3
"""

from __future__ import annotations

import dataclasses
import math
from typing import List

from .domain import Outcome

SATURATION_NEW_SOURCES = 2
SATURATION_CONF_DELTA = 0.03
BUDGET_STOP_FRACTION = 0.95


@dataclasses.dataclass
class Quality:
    rqs: float
    components: dict


def compute_rqs(conn, mid: str, prof, a) -> Quality:
    groups = (a.independence or {}).get("independent_groups", 0)
    ev = conn.execute(
        "SELECT count(*) FILTER (WHERE source_id IS NOT NULL) AS src, "
        "count(*) FILTER (WHERE source_id IS NOT NULL AND quote_verified) AS ver FROM evidence WHERE mission_id=%s",
        (mid,)).fetchone()
    verified = (ev["ver"] / ev["src"]) if ev["src"] else 0.0
    con = conn.execute("SELECT count(*) AS n, count(*) FILTER (WHERE resolution<>'UNRESOLVED') AS r "
                       "FROM contradictions WHERE mission_id=%s", (mid,)).fetchone()
    resolved = (con["r"] / con["n"]) if con["n"] else 1.0
    cr = conn.execute("SELECT avg(score) AS s FROM critic_reports WHERE mission_id=%s AND iteration = "
                      "(SELECT max(iteration) FROM critic_reports WHERE mission_id=%s)", (mid, mid)).fetchone()
    critic = float(cr["s"]) if cr and cr["s"] is not None else 0.5
    if prof.max_experiments == 0:
        exper = 0.5
    else:
        x = conn.execute(
            "SELECT count(*) FILTER (WHERE status='COMPLETED') AS done, "
            "count(*) FILTER (WHERE status='COMPLETED' AND reproducibility IS NOT NULL) AS rep, "
            "count(*) FILTER (WHERE status='PHYSICAL_EXPERIMENT_REQUIRED') AS phys FROM experiments WHERE mission_id=%s",
            (mid,)).fetchone()
        exper = 0.0 if not (x["done"] or x["phys"]) else (0.5 * min(1, x["done"]) + 0.5 * min(1, x["rep"]))
        if x["phys"] and not x["done"]:
            exper = 0.3
    prov = conn.execute("SELECT count(DISTINCT provider) AS n FROM sources WHERE mission_id=%s AND analyzed",
                        (mid,)).fetchone()["n"]
    comps = {
        "independence": min(1.0, groups / max(1, min(prof.max_sources, 8))),
        "verification": verified,
        "evidence_mass": 1 - math.exp(-a.n_eff / 3.0),
        "contradictions_resolved": resolved,
        "criticism": max(0.0, min(1.0, critic)),
        "experiments": exper,
        "provider_diversity": min(1.0, prov / 3.0),
    }
    w = {"independence": .20, "verification": .15, "evidence_mass": .20, "contradictions_resolved": .10,
         "criticism": .15, "experiments": .10, "provider_diversity": .10}
    rqs = sum(comps[k] * w[k] for k in w)
    return Quality(round(rqs, 4), {k: round(v, 4) for k, v in comps.items()})


def saturated(iteration: int, new_sources: int, conf_delta: float) -> bool:
    """Spec 42: another cycle found almost nothing new and moved confidence by < 3 points."""
    return iteration >= 1 and new_sources < SATURATION_NEW_SOURCES and abs(conf_delta) < SATURATION_CONF_DELTA


@dataclasses.dataclass
class Decision:
    outcome: str
    reasons: List[str]

    def as_dict(self) -> dict:
        return {"outcome": self.outcome, "reasons": self.reasons}


def decide(*, prof, iteration: int, elapsed_s: float, tasks_used: int, confidence: float, rqs: float,
           physical_required: bool, physical_approved: bool, is_saturated: bool) -> Decision:
    if elapsed_s >= prof.time_budget_s:
        return Decision(str(Outcome.STOP_TIME_LIMIT), [f"time budget {prof.time_budget_s}s reached"])
    if tasks_used >= BUDGET_STOP_FRACTION * prof.max_tasks:
        return Decision(str(Outcome.STOP_BUDGET), [f"{tasks_used}/{prof.max_tasks} tasks used"])
    if physical_required and not physical_approved:
        return Decision(str(Outcome.BLOCKED_EXTERNAL_EXPERIMENT),
                        ["the hypothesis can only be tested by a physical experiment; human approval needed"])
    done = iteration + 1
    if done < prof.min_iterations:
        return Decision(str(Outcome.CONTINUE), [f"minimum {prof.min_iterations} research cycles not reached"])
    if confidence >= prof.evidence_threshold and rqs >= prof.rqs_threshold:
        return Decision(str(Outcome.STOP_CONFIDENT),
                        [f"confidence {confidence:.2f} >= {prof.evidence_threshold:.2f}",
                         f"research quality {rqs:.2f} >= {prof.rqs_threshold:.2f}"])
    why = []
    if confidence < prof.evidence_threshold:
        why.append(f"confidence {confidence:.2f} < {prof.evidence_threshold:.2f}")
    if rqs < prof.rqs_threshold:
        why.append(f"research quality {rqs:.2f} < {prof.rqs_threshold:.2f}")
    if done >= prof.max_iterations:
        return Decision(str(Outcome.STOP_WITH_UNCERTAINTY), why + [f"max {prof.max_iterations} cycles reached"])
    if is_saturated:
        return Decision(str(Outcome.STOP_WITH_UNCERTAINTY), why + ["evidence saturated: new cycles add nothing"])
    return Decision(str(Outcome.CONTINUE), why)
