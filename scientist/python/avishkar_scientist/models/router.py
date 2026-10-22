"""TierRouter -- Scientist OS's model gateway on top of avishkar_router.

Decision D3 (owner): the local 4B does the everyday work; Gemini is used
ONLY for key / high-priority / final decisions; OpenRouter is the fallback
when Gemini fails. That is encoded as *purposes*: a call names what it is
for, and only the purposes in PREMIUM_PURPOSES may reach Tier 3+. Even
those are subject to the budget gate (models/budget.py) and are downgraded
to the local model when a cap is hit or the depth's allowance is zero
(QUICK = 0 premium calls).

Every call -- ok, failed, cached, downgraded, denied -- lands in the
model_calls ledger (spec section 24).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from typing import Callable, List, Optional, Sequence

from avishkar_router import (CompletionRequest, Message, ModelSpec, Router, RoutingPolicy,
                             RoutingRule)
from avishkar_router.errors import RouterError
from avishkar_router.provider import ModelProvider
from avishkar_router.providers.openai_compatible_provider import OpenAICompatibleProvider
from avishkar_router.types import ProviderResponse

from ..config import Settings
from ..domain import Tier
from ..storage.db import Database
from . import budget as budget_mod
from . import cache as cache_mod
from .embed import Embedder

# purpose -> minimum tier it is *allowed* to use. Anything not listed is local.
PREMIUM_PURPOSES = {
    "plan_review": Tier.T3_STRONG,               # DEEP/EXTREME research plan sanity check
    "contradiction_resolution": Tier.T3_STRONG,  # HIGH-severity contradictions only
    "evidence_sufficiency": Tier.T3_STRONG,      # is the evidence enough to stop?
    "council_judge_a": Tier.T3_STRONG,           # Gemini judge
    "council_judge_b": Tier.T3_STRONG,           # OpenRouter judge (independent family)
    "verdict_narrative": Tier.T3_STRONG,         # final verdict text
    "final_verdict": Tier.T4_PREMIUM,            # DEEP/EXTREME final verdict
    "coder_patch": Tier.T3_STRONG,               # autonomous coder: generate a code fix
    "dspy_label": Tier.T3_STRONG,                # DSPy: judge which tool a past turn should have used
}

LOCAL_MODEL = "local-triage"
CHAIN_T3 = ("gemini-3.7-flash", "gemini-3.8-flash", "gemini-flash-latest", "openai/gpt-4o-mini")
CHAIN_T4 = ("gemini-3.1-pro-preview", "openai/gpt-4o") + CHAIN_T3
CHAIN_JUDGE_B = ("openai/gpt-4o-mini", "openai/gpt-4o")

# Estimated list prices (USD per 1M tokens) used for the budget ledger.
# Deliberately conservative: overestimating only makes caps trip earlier.
_PRICES = {
    "gemini-3.7-flash": (0.50, 3.00), "gemini-3.8-flash": (0.50, 3.00), "gemini-flash-latest": (0.50, 3.00),
    "gemini-3.1-pro-preview": (2.50, 15.00),
    "openai/gpt-4o-mini": (0.15, 0.60), "openai/gpt-4o": (2.50, 10.00),
}

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


class ModelUnavailable(Exception):
    """No model could serve the request -- callers use their deterministic path."""


@dataclasses.dataclass
class ModelResult:
    content: str
    model: str
    provider: str
    tier: int
    cost_usd: float
    status: str               # ok | cache_hit | semantic_hit | downgraded
    note: str = ""

    def json(self):
        return extract_json(self.content)


def extract_json(text: str):
    """First JSON object/array in a model reply (tolerates fences and prose)."""
    if not text:
        return None
    text = _THINK.sub("", text)
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidates = [m.group(1)] if m else []
    candidates.append(text)
    for cand in candidates:
        for opener, closer in (("{", "}"), ("[", "]")):
            start = cand.find(opener)
            while start != -1:
                depth, in_str, esc = 0, False, False
                for i in range(start, len(cand)):
                    ch = cand[i]
                    if in_str:
                        if esc:
                            esc = False
                        elif ch == "\\":
                            esc = True
                        elif ch == '"':
                            in_str = False
                        continue
                    if ch == '"':
                        in_str = True
                    elif ch == opener:
                        depth += 1
                    elif ch == closer:
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(cand[start:i + 1])
                            except json.JSONDecodeError:
                                break
                start = cand.find(opener, start + 1)
    return None


def _transport(timeout: float, local_no_think: bool = False):
    def send(url, headers, body):
        if local_no_think:
            payload = json.loads(body)
            payload["chat_template_kwargs"] = {"enable_thinking": False}
            msgs = payload.get("messages") or []
            if msgs and msgs[0].get("role") == "system" and "/no_think" not in msgs[0]["content"]:
                msgs[0]["content"] += "\n/no_think"
            body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- configured endpoints
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
    return send


class ScriptedProvider(ModelProvider):
    """Deterministic in-process provider for tests and the offline demo.
    `fn(model_id, request) -> str`."""

    def __init__(self, name: str, model_ids: Sequence[str], fn: Callable[[str, CompletionRequest], str]):
        self.name = name
        self._fn = fn
        self._models = tuple(ModelSpec(m, name, ("chat",), 0.0, 0.0, 32000, 4096) for m in model_ids)

    def list_models(self):
        return self._models

    def complete(self, request, *, model_id):
        out = self._fn(model_id, request)
        if isinstance(out, Exception):
            raise out
        return ProviderResponse(content=out, input_tokens=len(str(request.messages)) // 4,
                                output_tokens=len(out) // 4, stop_reason="stop")


def _spec(model_id: str, provider: str, ctx: int = 128000, out: int = 8192) -> ModelSpec:
    pin, pout = _PRICES.get(model_id, (0.0, 0.0))
    return ModelSpec(model_id, provider, ("chat", "json"), pin, pout, ctx, out)


def build_providers(settings: Settings) -> List[ModelProvider]:
    providers: List[ModelProvider] = []
    if settings.local_llm_url and not settings.offline:
        providers.append(OpenAICompatibleProvider(
            "local", base_url=settings.local_llm_url, name="local",
            models=[ModelSpec(settings.local_llm_model, "local", ("chat",), 0.0, 0.0, 16000, 2048)],
            transport=_transport(180.0, local_no_think=True), supports_tools=False))
    if settings.gemini_api_key and not settings.offline:
        providers.append(OpenAICompatibleProvider(
            settings.gemini_api_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            name="gemini", transport=_transport(90.0), supports_tools=False,
            models=[_spec(m, "gemini", 1000000) for m in
                    ("gemini-3.7-flash", "gemini-3.8-flash", "gemini-flash-latest", "gemini-3.1-pro-preview")]))
    if settings.openrouter_api_key and not settings.offline:
        providers.append(OpenAICompatibleProvider(
            settings.openrouter_api_key, base_url="https://openrouter.ai/api/v1", name="openrouter",
            transport=_transport(90.0), supports_tools=False,
            extra_headers={"HTTP-Referer": "https://tryvanta.in", "X-Title": "Avishkar Scientist OS"},
            models=[_spec(m, "openrouter") for m in ("openai/gpt-4o-mini", "openai/gpt-4o")]))
    return providers


class TierRouter:
    def __init__(self, db: Optional[Database], settings: Settings,
                 providers: Optional[Sequence[ModelProvider]] = None,
                 embedder: Optional[Embedder] = None, local_model: Optional[str] = None):
        self.db = db
        self.settings = settings
        self.local_model = local_model or settings.local_llm_model or LOCAL_MODEL
        provs = list(providers) if providers is not None else build_providers(settings)
        self._registered = {spec.model_id for p in provs for spec in p.list_models()}
        policy = RoutingPolicy(default_model=self.local_model, rules=(
            RoutingRule(models=(self.local_model,), task_type="local"),
            RoutingRule(models=CHAIN_T3, task_type="t3"),
            RoutingRule(models=CHAIN_T4, task_type="t4"),
            RoutingRule(models=CHAIN_JUDGE_B, task_type="judge_b"),
        ))
        self._router = Router(provs, policy) if provs else None
        self.embedder = embedder or Embedder(None if settings.offline else settings.embed_url, settings.embed_model)

    # -- capability queries ---------------------------------------------------
    @property
    def local_available(self) -> bool:
        return self.local_model in self._registered

    @property
    def premium_available(self) -> bool:
        return any(m in self._registered for m in CHAIN_T3 + CHAIN_T4)

    # -- main entry ---------------------------------------------------------
    def complete(self, purpose: str, system: str, user: str, *, mission_id: Optional[str] = None,
                 task_id: Optional[int] = None, want_tier: Optional[int] = None,
                 max_tokens: int = 1200, temperature: float = 0.1, cache: bool = True) -> ModelResult:
        allowed = PREMIUM_PURPOSES.get(purpose)
        # non-premium purposes are always local, whatever the caller asked for
        tier = int(Tier.T1_LOCAL) if allowed is None else int(want_tier if want_tier is not None else allowed)
        if tier < 3:
            tier = int(Tier.T1_LOCAL)
        note = ""
        if tier >= 3:
            route = "judge_b" if purpose == "council_judge_b" else ("t4" if tier >= 4 else "t3")
            if not any(m in self._registered for m in {"t3": CHAIN_T3, "t4": CHAIN_T4, "judge_b": CHAIN_JUDGE_B}[route]):
                note = "no premium provider configured"
                tier, route = int(Tier.T1_LOCAL), "local"
            elif self.db is not None:
                with self.db.tx() as c:
                    d = budget_mod.premium_decision(
                        c, mission_id, daily_usd=self.settings.daily_premium_usd,
                        daily_calls=self.settings.daily_premium_calls, est_usd=0.01 if tier == 3 else 0.06)
                if not d.allowed:
                    note = d.reason
                    tier, route = int(Tier.T1_LOCAL), "local"
        else:
            route = "local"

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        key = cache_mod.result_key(purpose, route, messages)
        if cache and self.db is not None:
            with self.db.tx() as c:
                hit = cache_mod.get_result(c, key)
            if hit:
                self._ledger(mission_id, task_id, purpose, tier, hit.get("provider"), hit.get("model"),
                             "cache_hit", 0, 0, 0.0, 0, None)
                return ModelResult(hit["content"], hit["model"], hit["provider"], tier, 0.0, "cache_hit", note)

        emb = None
        if tier >= 3 and cache and self.db is not None and self.embedder.available:
            vecs = self.embedder.embed([system[-500:] + "\n" + user])
            if vecs:
                emb = vecs[0]
                with self.db.tx() as c:
                    hit = cache_mod.get_semantic(c, purpose, emb)
                if hit:
                    self._ledger(mission_id, task_id, purpose, tier, hit.get("provider"), hit.get("model"),
                                 "semantic_hit", 0, 0, 0.0, 0, None)
                    return ModelResult(hit["content"], hit["model"], hit["provider"], tier, 0.0, "semantic_hit", note)

        if self._router is None or (route == "local" and not self.local_available):
            self._ledger(mission_id, task_id, purpose, tier, None, None, "error", 0, 0, 0.0, 0,
                         "no model available" + (f" ({note})" if note else ""))
            raise ModelUnavailable("no model available for purpose " + purpose)

        req = CompletionRequest(
            messages=(Message("system", system), Message("user", user)),
            task_type=route, max_tokens=max_tokens,
            metadata={"temperature": temperature, "caller": f"scientist:{purpose}"})
        t0 = time.monotonic()
        try:
            resp = self._router.route(req)
        except RouterError as exc:
            self._ledger(mission_id, task_id, purpose, tier, None, None, "error", 0, 0, 0.0,
                         int((time.monotonic() - t0) * 1000), str(exc)[:800])
            if route != "local" and self.local_available:
                # premium chain fully failed -> one local attempt rather than nothing
                return self.complete("local_fallback:" + purpose, system, user, mission_id=mission_id,
                                     task_id=task_id, max_tokens=max_tokens, temperature=temperature, cache=cache)
            raise ModelUnavailable(str(exc)) from exc

        content = _THINK.sub("", resp.content or "").strip()
        premium = resp.provider_used in ("gemini", "openrouter")
        real_tier = tier if premium else int(Tier.T1_LOCAL)
        status = "downgraded" if note and not premium else "ok"
        self._ledger(mission_id, task_id, purpose, real_tier, resp.provider_used, resp.model_used, status,
                     resp.input_tokens, resp.output_tokens, resp.cost_usd, int(resp.latency_ms),
                     note or None, premium=premium)
        payload = {"content": content, "model": resp.model_used, "provider": resp.provider_used}
        if cache and self.db is not None and content:
            with self.db.tx() as c:
                cache_mod.put_result(c, key, purpose, payload)
                if emb is not None and premium:
                    cache_mod.put_semantic(c, purpose, key, emb, payload)
        return ModelResult(content, resp.model_used, resp.provider_used, real_tier, resp.cost_usd, status, note)

    def complete_json(self, purpose: str, system: str, user: str, **kw):
        """complete() + JSON parse; returns (parsed_or_None, ModelResult)."""
        res = self.complete(purpose, system + "\nRespond with JSON only.", user, **kw)
        return res.json(), res

    # -- ledger ---------------------------------------------------------------
    def _ledger(self, mission_id, task_id, purpose, tier, provider, model, status, tin, tout, cost, ms, err,
                premium: bool = False) -> None:
        if self.db is None:
            return
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO model_calls(mission_id, task_id, purpose, tier, provider, model, status, input_tokens, "
                "output_tokens, cost_usd, latency_ms, error) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (mission_id, task_id, purpose, tier, provider, model, status, tin, tout, cost, ms, err))
            if status in ("ok", "downgraded") and mission_id:
                budget_mod.record_usage(c, mission_id, premium=premium, cost_usd=cost)


def prompt_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
