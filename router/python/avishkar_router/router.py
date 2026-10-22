"""Router -- orchestrates provider selection, fallback, timing, and cost
tracking. See CONTRACT.md SS4.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .errors import DuplicateModelError, NoAvailableProviderError, NoMatchingModelError, ProviderError
from .policy import RoutingPolicy
from .provider import ModelProvider
from .types import CompletionRequest, CompletionResponse, ModelSpec

try:
    from avishkar_core import EventBus, Logger, get_logger
except ImportError:  # pragma: no cover - avishkar_core is a hard dependency
    # in pyproject.toml; this fallback only matters if someone runs this
    # file outside its packaged environment (e.g. ad hoc scripting).
    EventBus = None  # type: ignore[assignment,misc]
    Logger = None  # type: ignore[assignment,misc]

    def get_logger(name: str):  # type: ignore[no-redef]
        import logging

        return logging.getLogger(name)


class CostTracker:
    """Accumulates spend per calling module (`request.metadata["caller"]`)
    and in total. See CONTRACT.md SS4.
    """

    def __init__(self) -> None:
        self._total = 0.0
        self._by_caller: Dict[str, float] = {}

    def record(self, cost_usd: float, caller: Optional[str]) -> None:
        self._total += cost_usd
        if caller:
            self._by_caller[caller] = self._by_caller.get(caller, 0.0) + cost_usd

    def total_cost_usd(self, caller: Optional[str] = None) -> float:
        if caller is None:
            return self._total
        return self._by_caller.get(caller, 0.0)


class Router:
    """Routes a CompletionRequest to the first working candidate model per
    its RoutingPolicy, tracking cost and latency along the way.
    """

    def __init__(
        self,
        providers: Sequence[ModelProvider],
        policy: RoutingPolicy,
        *,
        event_bus: Optional[Any] = None,
        cost_tracker: Optional[CostTracker] = None,
        logger: Optional[Any] = None,
    ) -> None:
        self._models: Dict[str, Tuple[ModelProvider, ModelSpec]] = {}
        for provider in providers:
            for spec in provider.list_models():
                if spec.model_id in self._models:
                    raise DuplicateModelError(
                        f"Model '{spec.model_id}' is published by both "
                        f"'{self._models[spec.model_id][0].name}' and '{provider.name}' -- "
                        f"a Router refuses an ambiguous registry rather than picking one"
                    )
                self._models[spec.model_id] = (provider, spec)
        self._policy = policy
        self._event_bus = event_bus
        self._cost_tracker = cost_tracker or CostTracker()
        self._logger = logger or get_logger("router")

    @property
    def cost_tracker(self) -> CostTracker:
        return self._cost_tracker

    def list_models(self) -> Tuple[ModelSpec, ...]:
        return tuple(spec for _, spec in self._models.values())

    def route(self, request: CompletionRequest) -> CompletionResponse:
        candidates = self._policy.select_candidates(request)
        caller = request.metadata.get("caller") if request.metadata else None
        failures: List[str] = []
        any_registered = False

        for model_id in candidates:
            entry = self._models.get(model_id)
            if entry is None:
                failures.append(f"{model_id}: not registered with this router")
                continue
            any_registered = True
            provider, spec = entry

            start = time.monotonic()
            try:
                result = provider.complete(request, model_id=model_id)
            except ProviderError as exc:
                elapsed_ms = (time.monotonic() - start) * 1000
                failures.append(f"{model_id} ({provider.name}): {type(exc).__name__}: {exc}")
                self._logger.warning(
                    "Provider call failed, trying next candidate",
                    model=model_id,
                    provider=provider.name,
                    error_type=type(exc).__name__,
                    latency_ms=round(elapsed_ms, 2),
                )
                if self._event_bus is not None:
                    self._event_bus.publish(
                        "router.fallback",
                        {"model": model_id, "provider": provider.name, "error_type": type(exc).__name__},
                        source="router",
                    )
                continue

            elapsed_ms = (time.monotonic() - start) * 1000
            cost_usd = (
                result.input_tokens / 1_000_000 * spec.input_cost_per_mtok
                + result.output_tokens / 1_000_000 * spec.output_cost_per_mtok
            )
            self._cost_tracker.record(cost_usd, caller)

            self._logger.info(
                "Request routed",
                model=model_id,
                provider=provider.name,
                cost_usd=round(cost_usd, 6),
                latency_ms=round(elapsed_ms, 2),
            )
            if self._event_bus is not None:
                self._event_bus.publish(
                    "router.request.completed",
                    {"model": model_id, "provider": provider.name, "cost_usd": cost_usd, "caller": caller},
                    source="router",
                )

            return CompletionResponse(
                content=result.content,
                model_used=model_id,
                provider_used=provider.name,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=cost_usd,
                latency_ms=elapsed_ms,
                stop_reason=result.stop_reason,
                request_id=result.request_id,
                tool_calls=result.tool_calls,  # Phase 1
            )

        if not any_registered:
            raise NoMatchingModelError(
                f"No candidate model for this request is registered with this router: {failures}"
            )
        raise NoAvailableProviderError(
            f"All {len(candidates)} candidate model(s) failed: {failures}"
        )
