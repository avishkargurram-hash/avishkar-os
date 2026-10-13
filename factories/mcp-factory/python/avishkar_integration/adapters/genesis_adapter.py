"""GenesisServiceAdapter -- the keystone that absorbs Genesis's ~235
thin-wrapped services into Layla's Universal Integration Framework as
first-class tools, WITHOUT importing any of Genesis's own registry,
governance, event bus, or brain.

Every Genesis service reduces to one shape: a callable that takes a single
params dict and returns a normalized dict
    {"status": "success"|"error", "data"/"error"/"message": ...}
reached either as a module-level function (`run(params)` / `execute(params)`,
the Google/function style) or as a method on a service class (`check_status`,
the IoT/homelab style). This adapter resolves either entrypoint, invokes it,
and normalizes the outcome -- including a service-raised exception -- into a
Layla `ToolExecutionResult`.

Once a service is published as a `ToolContract` and this adapter is registered
with a `UniversalToolRegistry`, Genesis's service inherits Layla's entire
safety stack for free: CapabilityResolver can route to it, risk.classify_risk
tiers it, ApprovalManager gates it, ExecutionTracker makes it idempotent.
None of Genesis's `tool_registry.py` / `event_bus.py` / `brain_chain.py`
comes along.

A service is DECLARED, not discovered (mirroring RESTAdapter). Each
ToolContract's `protocol_config` says how to reach the callable:

    {"module": "core.services.iot.nodered_service",  # dotted import  -OR-
     "module_path": r"C:/.../nodered_service.py",      # load by file path
     "class": "NodeREDService",                         # optional; class style
     "method": "check_status",                          # method (class style)...
     "callable": "run"}                                 # ...or module-level fn
"""

from __future__ import annotations

import importlib
import importlib.util
import time
from typing import Any, Dict, Mapping, Sequence, Tuple

from ..errors import ProtocolInvocationError
from ..protocol import ProtocolAdapter
from ..types import ToolContract, ToolExecutionRequest, ToolExecutionResult


class GenesisServiceAdapter(ProtocolAdapter):
    protocol_name = "genesis"

    def __init__(self, tools: Sequence[ToolContract] = ()) -> None:
        self._tools: Dict[str, ToolContract] = {t.identity: t for t in tools}
        self._module_cache: Dict[str, Any] = {}

    # -- declaration / discovery -------------------------------------------
    def register_tool(self, contract: ToolContract) -> None:
        self._tools[contract.identity] = contract

    def discover_tools(self) -> Tuple[ToolContract, ...]:
        return tuple(self._tools.values())

    # -- module + entrypoint resolution ------------------------------------
    def _load_module(self, config: Mapping[str, Any]) -> Any:
        module_path = config.get("module_path")
        dotted = config.get("module")
        key = module_path or dotted
        if key is None:
            raise ProtocolInvocationError(
                "genesis service contract needs 'module' or 'module_path' in protocol_config"
            )
        if key in self._module_cache:
            return self._module_cache[key]
        try:
            if module_path:
                # Load a clean-leaf service directly by file path -- no
                # `core.__init__` boot, no Genesis runtime pulled in.
                name = "genesis_svc_" + str(abs(hash(module_path)))
                spec = importlib.util.spec_from_file_location(name, module_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"could not build import spec for {module_path}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            else:
                module = importlib.import_module(dotted)
        except Exception as exc:  # noqa: BLE001 -- normalized into our hierarchy
            raise ProtocolInvocationError(
                f"failed to import genesis service '{key}': {exc}"
            ) from exc
        self._module_cache[key] = module
        return module

    def _resolve_callable(self, module: Any, config: Mapping[str, Any]):
        cls_name = config.get("class")
        if cls_name:
            cls = getattr(module, cls_name, None)
            if cls is None:
                raise ProtocolInvocationError(
                    f"class '{cls_name}' not found in genesis service module"
                )
            instance = cls()  # Genesis service classes take no constructor args
            method = config.get("method") or "run"
            fn = getattr(instance, method, None)
            if fn is None:
                raise ProtocolInvocationError(
                    f"method '{method}' not found on '{cls_name}'"
                )
            return fn
        # module-level function style
        entry = config.get("callable") or config.get("method") or "run"
        fn = getattr(module, entry, None)
        if fn is None:
            raise ProtocolInvocationError(
                f"callable '{entry}' not found in genesis service module"
            )
        return fn

    # -- invocation + normalization ----------------------------------------
    def invoke(self, contract: ToolContract, request: ToolExecutionRequest) -> ToolExecutionResult:
        config = contract.protocol_config
        module = self._load_module(config)          # wiring failure -> raises
        fn = self._resolve_callable(module, config)  # wiring failure -> raises

        params = request.input if request.input is not None else {}
        takes_arg = config.get("takes_params", True)

        start = time.monotonic()
        try:
            raw = fn(params) if takes_arg else fn()
        except Exception as exc:  # noqa: BLE001
            # A service RAISING (missing token, host unreachable) is a normal
            # "service unavailable" outcome -- exactly what Genesis's own
            # tool wrappers catch and return as {status:error}. We mirror that:
            # an error RESULT, not a transport ProtocolInvocationError.
            elapsed = (time.monotonic() - start) * 1000
            return ToolExecutionResult(
                tool_identity=contract.identity,
                protocol=self.protocol_name,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=elapsed,
                attempts=1,
            )
        elapsed = (time.monotonic() - start) * 1000
        return self._normalize(contract, raw, elapsed)

    def _normalize(self, contract: ToolContract, raw: Any, elapsed: float) -> ToolExecutionResult:
        status = "success"
        output: Any = raw
        error = None
        if isinstance(raw, Mapping) and "status" in raw:
            svc_status = str(raw.get("status", "")).lower()
            if svc_status in ("error", "failed", "failure"):
                status = "error"
                error = raw.get("error") or raw.get("message") or str(raw)
                output = None
            else:
                output = raw.get("data", {k: v for k, v in raw.items() if k != "status"})
        return ToolExecutionResult(
            tool_identity=contract.identity,
            protocol=self.protocol_name,
            status=status,
            output=output,
            error=error,
            latency_ms=elapsed,
            attempts=1,
        )
