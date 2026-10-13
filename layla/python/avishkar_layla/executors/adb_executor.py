"""Real ADB (Android Debug Bridge) executor for EMBODIMENT_ADB. See
CONTRACT.md SS34.

STATUS: REAL CODE / ADAPTER READY. Genuinely shells out to a real
`adb` binary via `subprocess.run` -- not a simulation. No `adb` binary
and no connected Android device exist in this environment
(`is_adb_available()` correctly reports `False` here, verified by a
real test), so live device interaction is untested in this pass; per
Directive D's own explicit fallback for "an external credential,
hardware device, operating-system permission, or unavailable service,"
this is the honest boundary: real code, real dispatch logic (fully
tested via an injectable `_run` seam -- the same DI pattern
`ComputerControlExecutor`'s `_gui` uses), not a fabricated live
integration. EMBODIMENT_ADB is in embodiment.py's
`_DEFAULT_HIGH_RISK_CAPABILITIES` -- every action through this
executor always requires approval before `EmbodimentController` even
looks it up, same as EMBODIMENT_COMPUTER_CONTROL. `shell` additionally
requires its own allowlist here (mirroring
`ComputerControlExecutor.run_shell`) -- an arbitrary command on a real
phone is exactly as dangerous as one on the host, and deserves the
same fail-closed default.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any, Callable, List, Mapping, Optional, Sequence

from .errors import ADBNotAvailableError, ShellCommandNotAllowedError, UnknownActionError

_ACTIONS = (
    "list_devices", "device_info", "screenshot", "shell", "tap", "install_app", "launch_app",
    "push_file", "pull_file",
)


def is_adb_available(*, adb_path: str = "adb") -> bool:
    """Real check: is the `adb` binary discoverable on PATH? Does not
    require a connected device -- `list_devices` can legitimately
    return an empty list.
    """
    return shutil.which(adb_path) is not None


class ADBExecutor:
    def __init__(
        self, *, adb_path: str = "adb", device_serial: Optional[str] = None, timeout_seconds: float = 30.0,
        allowed_shell_commands: Sequence[str] = (), max_output_chars: int = 20000,
        _run: Optional[Callable[[List[str], float], "subprocess.CompletedProcess"]] = None,
    ) -> None:
        self._adb_path = adb_path
        self._device_serial = device_serial
        self._timeout_seconds = timeout_seconds
        self._allowed_shell_commands = frozenset(allowed_shell_commands)
        self._max_output_chars = max_output_chars
        self._run = _run or self._real_run

    def _real_run(self, args: List[str], timeout: float) -> "subprocess.CompletedProcess":
        if not is_adb_available(adb_path=self._adb_path):
            raise ADBNotAvailableError(
                f"the 'adb' binary ({self._adb_path!r}) is not installed/discoverable on this machine -- "
                f"this is the documented ADAPTER READY boundary (CONTRACT.md SS34): install Android "
                f"platform-tools and connect a device before using ADBExecutor in production."
            )
        cmd = [self._adb_path]
        if self._device_serial:
            cmd += ["-s", self._device_serial]
        cmd += args
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def _result(self, proc: "subprocess.CompletedProcess") -> Mapping[str, Any]:
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout[: self._max_output_chars],
            "stderr": proc.stderr[: self._max_output_chars],
        }

    def __call__(self, action: str, parameters: Mapping[str, Any]) -> Any:
        if action not in _ACTIONS:
            raise UnknownActionError(f"ADBExecutor has no action {action!r} -- expected one of {_ACTIONS}")

        timeout = parameters.get("timeout_seconds", self._timeout_seconds)

        if action == "list_devices":
            proc = self._run(["devices", "-l"], timeout)
            lines = [line.strip() for line in proc.stdout.splitlines()[1:] if line.strip()]
            return {"devices": lines, "raw": self._result(proc)}

        if action == "device_info":
            proc = self._run(["shell", "getprop"], timeout)
            return self._result(proc)

        if action == "screenshot":
            proc = self._run(["exec-out", "screencap", "-p"], timeout)
            return {"png_bytes": proc.stdout, "returncode": proc.returncode}

        if action == "shell":
            command = parameters["command"]
            program = command.strip().split()[0] if command.strip() else ""
            if not self._allowed_shell_commands or program not in self._allowed_shell_commands:
                raise ShellCommandNotAllowedError(
                    f"adb shell command {command!r} (program {program!r}) is not in this executor's "
                    f"allowlist {sorted(self._allowed_shell_commands)!r} -- fail closed, no default allowlist"
                )
            proc = self._run(["shell", command], timeout)
            return self._result(proc)

        if action == "tap":
            proc = self._run(["shell", "input", "tap", str(parameters["x"]), str(parameters["y"])], timeout)
            return self._result(proc)

        if action == "install_app":
            proc = self._run(["install", "-r", parameters["apk_path"]], timeout)
            return self._result(proc)

        if action == "launch_app":
            package = parameters["package"]
            activity = parameters.get("activity", "1")
            proc = self._run(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", activity], timeout)
            return self._result(proc)

        if action == "push_file":
            proc = self._run(["push", parameters["local_path"], parameters["device_path"]], timeout)
            return self._result(proc)

        if action == "pull_file":
            proc = self._run(["pull", parameters["device_path"], parameters["local_path"]], timeout)
            return self._result(proc)

        raise UnknownActionError(f"unhandled ADB action {action!r}")  # pragma: no cover
