"""Deterministic DEMO research world (spec section 50).

Used ONLY by demo missions (SCI-DEMO-001) and offline tests. Every record is
about a fictional material ("Demonium-7") so nothing here can be mistaken
for a real paper: provider is `demo_simulated`, titles carry a `[SIMULATED]`
prefix, DOIs live under the reserved `10.0000/` prefix, and the report for
any mission that used them is stamped "DEMO -- SIMULATED".

The demo also ships a fixed plan, fixed claim extractions (quotes are real
substrings of the simulated abstracts and still pass quote verification)
and one canned, human-written computational experiment, so the whole
pipeline -- queues, workers, evidence, contradictions, critics, sandbox,
termination, verdict, report -- runs with zero LLM calls.
"""

from __future__ import annotations

from .literature import _rec

DEMO_MISSION_ID = "SCI-DEMO-001"
DEMO_QUESTION = ("Is ambient-pressure superconductivity above 200 K feasible in the fictional "
                 "layered hydride Demonium-7 under standard laboratory conditions?")

_PAPERS = [
    dict(external_id="demo-001", doi="10.0000/demo.001", year=2024, citation_count=41,
         authors=["A. Demo-Rao", "B. Demo-Iyer"],
         title="Ambient-pressure resistive transition near 215 K in Demonium-7 thin films",
         venue="Demo Journal of Condensed Matter",
         abstract=("We report a resistive drop in Demonium-7 thin films near 215 K at ambient pressure. "
                   "The transition is suppressed by an applied magnetic field of 2 T. "
                   "No Meissner fraction was measured in this study."),
         referenced=[]),
    dict(external_id="demo-002", doi="10.0000/demo.002", year=2024, citation_count=18,
         authors=["C. Demo-Khan", "D. Demo-Lee"],
         title="Absence of diamagnetic shielding in bulk Demonium-7 down to 10 K",
         venue="Demo Physical Review",
         abstract=("Magnetization measurements on bulk Demonium-7 show no diamagnetic shielding down to 10 K. "
                   "The resistive anomaly near 215 K coincides with a structural transition of a copper "
                   "sulfide impurity phase."),
         referenced=["10.0000/demo.001"]),
    dict(external_id="demo-003", doi="10.0000/demo.003", year=2025, citation_count=9,
         authors=["E. Demo-Sato"],
         title="First-principles phonon calculations rule out conventional pairing in Demonium-7",
         venue="Demo Computational Materials",
         abstract=("Density functional calculations give an electron-phonon coupling constant of 0.31 for "
                   "Demonium-7, which predicts a conventional critical temperature below 5 K. "
                   "Ambient-pressure superconductivity above 200 K is not supported by conventional pairing."),
         referenced=["10.0000/demo.001"]),
    dict(external_id="demo-004", doi="10.0000/demo.004", year=2025, citation_count=3,
         authors=["F. Demo-Okafor", "G. Demo-Silva"],
         title="Independent replication: Demonium-7 resistive drop traced to impurity phase",
         venue="Demo Letters",
         abstract=("An independent group synthesized phase-pure Demonium-7 and observed no resistive drop "
                   "between 100 K and 300 K. Samples containing the copper sulfide impurity reproduce "
                   "the 215 K anomaly."),
         referenced=["10.0000/demo.002"]),
    dict(external_id="demo-005", doi="10.0000/demo.005", year=2025, citation_count=1,
         authors=["H. Demo-Novak"],
         title="Preprint: possible unconventional pairing channel in strained Demonium-7",
         venue="demoRxiv", source_type="preprint",
         abstract=("We speculate that epitaxial strain could open an unconventional pairing channel in "
                   "Demonium-7. This mechanism has not been tested experimentally."),
         referenced=[]),
]

# external_id -> [(quote, stance toward H1, epistemic, strength)]
DEMO_CLAIMS = {
    "demo-001": [("We report a resistive drop in Demonium-7 thin films near 215 K at ambient pressure.",
                  "SUPPORTS", "OBSERVATION", 0.6)],
    "demo-002": [("Magnetization measurements on bulk Demonium-7 show no diamagnetic shielding down to 10 K.",
                  "REFUTES", "OBSERVATION", 0.9),
                 ("The resistive anomaly near 215 K coincides with a structural transition of a copper sulfide "
                  "impurity phase.", "REFUTES", "OBSERVATION", 0.7)],
    "demo-003": [("Ambient-pressure superconductivity above 200 K is not supported by conventional pairing.",
                  "REFUTES", "INFERENCE", 0.6)],
    "demo-004": [("An independent group synthesized phase-pure Demonium-7 and observed no resistive drop "
                  "between 100 K and 300 K.", "REFUTES", "OBSERVATION", 0.9)],
    "demo-005": [("We speculate that epitaxial strain could open an unconventional pairing channel in "
                  "Demonium-7.", "SUPPORTS", "SPECULATION", 0.2)],
}

DEMO_PLAN = {
    "h1": "Demonium-7 is a superconductor with a critical temperature above 200 K at ambient pressure.",
    "h0": "Demonium-7 is not superconducting above 200 K at ambient pressure.",
    "alternatives": ["The 215 K resistive anomaly is an impurity-phase structural transition, not superconductivity."],
    "queries": ["Demonium-7 superconductivity ambient pressure", "Demonium-7 Meissner effect magnetization"],
    "physical_only": False,
    "experiment_idea": "McMillan estimate of Tc from the published electron-phonon coupling constant.",
}

# Human-written (not model-generated) program; still statically validated and
# executed only through the sandbox like any other experiment.
DEMO_EXPERIMENT = {
    "kind": "COMPUTATIONAL",
    "title": "McMillan-formula Tc estimate for Demonium-7 (lambda = 0.31)",
    "rationale": ("If pairing is conventional, the McMillan formula bounds Tc from the reported "
                  "electron-phonon coupling. A Tc far below 200 K argues against H1 under conventional pairing."),
    "support_criterion": 'result["tc_k"] > 200',
    "code": (
        "import math, json, random\n"
        "lam = 0.31          # electron-phonon coupling (simulated source demo-003)\n"
        "mu = 0.10           # Coulomb pseudopotential, conventional choice\n"
        "theta_d = 400.0     # Debye temperature in K (assumed, upper-range value)\n"
        "jitter = 1.0 + random.uniform(-0.01, 0.01)   # seed-dependent perturbation for replication\n"
        "denom = lam - mu * (1 + 0.62 * lam)\n"
        "tc = (theta_d * jitter / 1.45) * math.exp(-1.04 * (1 + lam) / denom)\n"
        "print('RESULT_JSON: ' + json.dumps({'tc_k': round(tc, 4), 'lambda': lam, 'mu_star': mu, "
        "'theta_d_k': theta_d}))\n"),
}


def demo_records(query: str = "", limit: int = 8) -> list:
    out = []
    for p in _PAPERS[:limit]:
        p = dict(p)
        out.append(_rec(provider="demo_simulated",
                        external_id=p.pop("external_id"),
                        doi=p.pop("doi"),
                        title="[SIMULATED] " + p.pop("title"),
                        url="", source_type=p.pop("source_type", "journal"),
                        is_retracted=False, **p))
    return out


def search_demo(query: str, limit: int = 8, timeout_s: float = 0) -> list:
    return demo_records(query, limit)
