"""Claim extraction (spec sections 15, 16, 44).

One local-model call per source (purpose `claim_extraction`). The model
must quote the abstract verbatim for every claim; a claim whose quote is
not a (normalized) substring of the stored abstract is DROPPED, so nothing
the model invents can become evidence. Demo sources use the fixed
DEMO_CLAIMS table. With no model available, real sources yield no claims
and the analysis output says so -- the report then shows fewer claims
rather than made-up ones.
"""

from __future__ import annotations

import dataclasses
from typing import List, Optional

from ..domain import Epistemic, Stance
from ..tools.mock import DEMO_CLAIMS
from .store import normalize_text

MAX_CLAIMS_PER_SOURCE = 4

SYSTEM = (
    "You are a careful research assistant extracting evidence for a scientific question. "
    "From the ABSTRACT, extract at most 4 claims that bear on the HYPOTHESIS. For each claim give: "
    "text (one sentence, your paraphrase), quote (an EXACT contiguous sentence or phrase copied from the abstract), "
    "stance toward the hypothesis (SUPPORTS | REFUTES | NEUTRAL), epistemic status "
    "(FACT | OBSERVATION | INFERENCE | HYPOTHESIS | SPECULATION) and strength 0..1 (how directly it bears on the "
    "hypothesis). Also give relevance 0..1 of the whole abstract to the question. Never add information not in "
    "the abstract. If nothing is relevant return an empty claims list. "
    'Schema: {"relevance": 0.0, "claims": [{"text": "", "quote": "", "stance": "", "epistemic": "", "strength": 0.0}]}'
)


@dataclasses.dataclass
class ExtractedClaim:
    text: str
    quote: str
    stance: str
    epistemic: str
    strength: float
    verified: bool


@dataclasses.dataclass
class Extraction:
    relevance: float
    claims: List[ExtractedClaim]
    extractor: str
    dropped: int = 0
    note: str = ""


def quote_in(quote: str, abstract: str) -> bool:
    q = normalize_text(quote)
    return len(q) >= 12 and q in normalize_text(abstract)


def _enum(value, enum_cls, default):
    try:
        return str(enum_cls(str(value).strip().upper()))
    except ValueError:
        return str(default)


def extract_demo(external_id: str) -> Extraction:
    claims = [ExtractedClaim(q, q, st, ep, s, True) for q, st, ep, s in DEMO_CLAIMS.get(external_id, [])]
    return Extraction(1.0 if claims else 0.0, claims, "deterministic:demo")


def extract_claims(router, *, question: str, hypothesis: str, title: str, abstract: str,
                   mission_id: Optional[str] = None, task_id: Optional[int] = None) -> Extraction:
    from ..models.router import ModelUnavailable
    if not abstract.strip():
        return Extraction(0.0, [], "none", note="no abstract available")
    user = f"QUESTION: {question}\nHYPOTHESIS: {hypothesis}\nTITLE: {title}\nABSTRACT: {abstract[:6000]}"
    try:
        data, res = router.complete_json("claim_extraction", SYSTEM, user, mission_id=mission_id,
                                         task_id=task_id, max_tokens=900)
    except ModelUnavailable as exc:
        return Extraction(0.0, [], "none", note=f"no model available: {exc}")
    if not isinstance(data, dict):
        return Extraction(0.0, [], f"{res.provider}:{res.model}", note="model reply was not valid JSON")
    out, dropped = [], 0
    for c in (data.get("claims") or [])[:MAX_CLAIMS_PER_SOURCE * 2]:
        if not isinstance(c, dict):
            continue
        quote = str(c.get("quote") or "").strip()
        text = str(c.get("text") or quote).strip()
        if not quote or not quote_in(quote, abstract):
            dropped += 1        # unverifiable -> never becomes evidence
            continue
        stance = _enum(c.get("stance"), Stance, Stance.NEUTRAL)
        if stance == "NEUTRAL":
            continue
        try:
            strength = max(0.0, min(1.0, float(c.get("strength", 0.5))))
        except (TypeError, ValueError):
            strength = 0.5
        out.append(ExtractedClaim(text[:600], quote[:1000], stance,
                                  _enum(c.get("epistemic"), Epistemic, Epistemic.OBSERVATION), strength, True))
        if len(out) >= MAX_CLAIMS_PER_SOURCE:
            break
    try:
        relevance = max(0.0, min(1.0, float(data.get("relevance", 0.5))))
    except (TypeError, ValueError):
        relevance = 0.5
    return Extraction(relevance, out, f"{res.provider}:{res.model}", dropped=dropped)
