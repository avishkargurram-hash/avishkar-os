"""Critic personas (spec section 21).

Each role reviews the mission's current evidence package from a different
angle. Purpose `critic_review` is not in PREMIUM_PURPOSES, so critics always
run on the local model (D3: Gemini is reserved for key decisions only) --
this is routine, repeated work. With no model available (or in demo mode)
a deterministic placeholder review is returned rather than failing the task.
"""

from __future__ import annotations

from ..models.router import ModelUnavailable

ROLE_FOCUS = {
    "scientific_critic": "whether the overall scientific reasoning and causal claims are sound",
    "skeptic": "alternative explanations and whether the evidence could be coincidence or bias",
    "evidence_auditor": "whether every claim is properly sourced, quoted and not overstated",
    "methodology_critic": "weaknesses in experiment design, statistics, and sample sizes",
    "logical_critic": "logical fallacies, non-sequiturs, or unsupported inferential leaps",
    "bias_detector": "selection bias, publication bias, and conflicts of interest in the sources",
}

SYSTEM = (
    "You are a {role}, a rigorous scientific critic. Focus specifically on {focus}. "
    "Given the research package JSON below, return a JSON object: "
    '{{"score": 0.0..1.0 (overall quality from your viewpoint), '
    '"issues": ["short specific issue", ...], "open_questions": ["short question", ...]}}. '
    "Be concrete; reference specific hypotheses or claims by label/id when possible. "
    "At most 5 issues and 5 open questions."
)


def deterministic_review(role: str, pkg: dict) -> dict:
    issues = []
    n_sources = len(pkg.get("sources") or [])
    if n_sources < 3:
        issues.append(f"only {n_sources} source(s) examined -- evidence base is thin")
    if pkg.get("contradictions"):
        issues.append(f"{len(pkg['contradictions'])} contradiction(s) in the evidence")
    if not pkg.get("experiments") and role in ("methodology_critic", "scientific_critic"):
        issues.append("no experiments were run to test the hypothesis directly")
    assessment = pkg.get("assessment") or {}
    score = round(float(assessment.get("confidence", 0.0)), 4)
    return {"score": score, "issues": issues[:5], "open_questions": [], "model": "deterministic:critic"}


def review(router, role: str, brief: str, pkg: dict, *, mission_id: str = None, task_id: int = None) -> dict:
    if router is None or pkg.get("demo"):
        return deterministic_review(role, pkg)
    system = SYSTEM.format(role=role.replace("_", " "), focus=ROLE_FOCUS.get(role, "general research quality"))
    try:
        data, res = router.complete_json("critic_review", system, brief, mission_id=mission_id,
                                         task_id=task_id, max_tokens=700)
    except ModelUnavailable:
        return deterministic_review(role, pkg)
    if not isinstance(data, dict):
        return deterministic_review(role, pkg)
    try:
        score = max(0.0, min(1.0, float(data.get("score", 0.5))))
    except (TypeError, ValueError):
        score = 0.5
    issues = [str(x)[:300] for x in (data.get("issues") or [])][:5]
    open_qs = [str(x)[:300] for x in (data.get("open_questions") or [])][:5]
    return {"score": score, "issues": issues, "open_questions": open_qs, "model": f"{res.provider}:{res.model}"}
