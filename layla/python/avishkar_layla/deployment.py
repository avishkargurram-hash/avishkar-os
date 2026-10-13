"""Production deployment boundary -- Mission Layla Directive D, Part
XVII (Production Deployment). See CONTRACT.md SS60.

Three real, testable capabilities, each a thin layer over already-real
components -- never a new orchestration system:

1. A real HTTP health server (stdlib `http.server`, no new dependency)
   exposing `GET /health` (a cheap liveness probe, `ExecutiveRuntime.
   is_alive()`) and `GET /health/report` (the full
   `build_production_health_report()` from Part XIV, as JSON) --
   exactly what a container orchestrator's liveness/readiness probes
   or a load balancer's health check needs, over a real socket.
2. Real graceful-shutdown signal wiring: `install_graceful_shutdown()`
   registers a handler for SIGINT/SIGTERM (SIGTERM only where the
   platform actually supports it) that calls the already-real
   `ExecutiveRuntime.request_shutdown()` -- never a bespoke shutdown
   path, and never `os._exit()`.
3. Real backup/restore for `FileMemoryPolicy`'s on-disk data directory
   -- `shutil.copytree` to/from a timestamped directory. No new
   storage format, no new backend; this operates on exactly the real
   `short_term.json`/`long_term.json`/`episodic.json`/`semantic.json`
   files `FileMemoryPolicy` already writes.

Config/secrets loading is NOT duplicated here: `avishkar_core.Config`
already implements the real layered defaults < file < env < overrides
precedence (CONTRACT.md SS1, core/, locked Phase 1) and is the correct
place for a deployment's environment-specific settings (see
`layla/OPERATIONS.md` for the DEVELOPMENT/TEST/STAGING/PRODUCTION
profile convention built on top of it, not duplicating it).

Containerization (`layla/Dockerfile`) and the operational runbook
(`layla/OPERATIONS.md`) are separate, non-Python artifacts -- see
README.md's Production Deployment section for what's real vs. what
requires an external dependency (a live container registry, a real
orchestrator) this environment cannot exercise end-to-end.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import shutil
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Union

from .observability import build_production_health_report

_DEFAULT_SIGNALS = ("SIGINT", "SIGTERM")


def _make_handler(runtime: Any, *, business_intelligence: Optional[Any], max_staleness_seconds: float) -> type:
    class _HealthHandler(BaseHTTPRequestHandler):
        # Real production servers don't want the stdlib's default
        # per-request stderr access log spam; keep the class quiet and
        # let a real deployment wire its own logging if it wants one.
        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003 - stdlib signature
            return

        def _write_json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib method name
            if self.path == "/health":
                alive = runtime.is_alive(max_staleness_seconds=max_staleness_seconds)
                self._write_json(200 if alive else 503, {"alive": alive})
            elif self.path == "/health/report":
                report = build_production_health_report(
                    runtime, business_intelligence=business_intelligence,
                    max_staleness_seconds=max_staleness_seconds,
                )
                self._write_json(200, dataclasses.asdict(report))
            else:
                self._write_json(404, {"error": "not found", "path": self.path})

    return _HealthHandler


class HealthServer:
    """A real, running HTTP server wrapping a stdlib `ThreadingHTTPServer`
    -- `start()`/`stop()` are real socket bind/accept-loop/close calls,
    not a simulation. `port=0` (the default) binds an OS-assigned
    ephemeral port, read back via `self.port` -- the same pattern this
    codebase's own local-fixture tests already use (see
    `test_home_assistant_executor.py`).
    """

    def __init__(
        self, runtime: Any, *, host: str = "127.0.0.1", port: int = 0,
        business_intelligence: Optional[Any] = None, max_staleness_seconds: float = 120.0,
    ) -> None:
        handler_cls = _make_handler(
            runtime, business_intelligence=business_intelligence, max_staleness_seconds=max_staleness_seconds,
        )
        self._httpd = ThreadingHTTPServer((host, port), handler_cls)
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=timeout)


def install_graceful_shutdown(
    runtime: Any, *, signals: Iterable[str] = _DEFAULT_SIGNALS,
    _signal_module: Any = signal,
) -> Callable[[], None]:
    """Registers a real `signal.signal()` handler for every name in
    `signals` that this platform actually has (Windows lacks several
    POSIX-only signals; each name is looked up via `getattr` and
    silently skipped if absent -- never a fabricated cross-platform
    shim). The handler calls the already-real
    `ExecutiveRuntime.request_shutdown()`, never a bespoke shutdown
    path or `os._exit()`.

    Returns the handler function itself, so a caller (or a test) can
    invoke it directly without needing to raise a real OS signal --
    the same DI-testability seam this whole Directive D pass has used
    throughout (`_signal_module` is the injectable seam for tests that
    want to assert `signal.signal` was called correctly without
    mutating the real process-wide signal table).
    """
    def _handler(signum: int, frame: Any) -> None:
        runtime.request_shutdown()

    for name in signals:
        sig = getattr(_signal_module, name, None)
        if sig is not None:
            _signal_module.signal(sig, _handler)
    return _handler


def backup_data_directory(root_dir: Union[str, Path], backup_root: Union[str, Path], *, clock: Optional[Callable[[], float]] = None) -> Path:
    """Real `shutil.copytree` of a `FileMemoryPolicy` `root_dir` into a
    new, timestamped subdirectory under `backup_root`. Returns the real
    path created. `clock`, if given, must return a real Unix timestamp
    (the same DI pattern as `Scheduler`/`ProactiveEngine`) -- used only
    to name the backup directory, never to fake the copy itself.
    """
    root_dir = Path(root_dir)
    backup_root = Path(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    now = clock() if clock is not None else datetime.datetime.now(datetime.timezone.utc).timestamp()
    stamp = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = backup_root / f"backup-{stamp}"
    shutil.copytree(root_dir, destination)
    return destination


def restore_data_directory(backup_dir: Union[str, Path], root_dir: Union[str, Path]) -> None:
    """Real restore: removes whatever currently exists at `root_dir`
    (if anything) and replaces it with a real copy of `backup_dir`'s
    contents. Destructive by design -- a caller performing a real
    restore is explicitly choosing to discard `root_dir`'s current
    state in favor of the backup's.
    """
    backup_dir = Path(backup_dir)
    root_dir = Path(root_dir)
    if root_dir.exists():
        shutil.rmtree(root_dir)
    shutil.copytree(backup_dir, root_dir)
