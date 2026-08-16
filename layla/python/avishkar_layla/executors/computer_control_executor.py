"""Real computer-control executor for EMBODIMENT_COMPUTER_CONTROL. See
CONTRACT.md SS34.

Three real sub-capabilities, each with a different testing posture:

- **Shell execution** (`run_shell`): REAL `subprocess.run`, gated by a
  caller-supplied allowlist (empty allowlist = nothing runs -- fail
  closed, no default allowlist of "safe" commands). Genuinely
  exercised in tests with harmless, real commands (`python -c
  "print(...)"`) -- this doesn't touch the visible desktop, so it's
  safe to run for real automatically.
- **File operations** (`read_file`/`write_file`/`list_dir`/
  `delete_file`): REAL, confined to a `workspace_root` via a real
  path-containment check (resolves symlinks/`..` and verifies the
  result is still inside the root) -- tested for real against a
  temporary directory, including real path-traversal attack strings.
- **GUI control** (`move_mouse`/`click`/`type_text`/`hotkey`/
  `screenshot`/clipboard): REAL `pyautogui`/`pyperclip` code, but --
  like voice's MicrophoneFrameSource and vision's capture_screen --
  moving the REAL mouse or typing on the REAL keyboard non-
  interactively during an unattended run would hijack this machine's
  actual desktop session. The `_gui` constructor parameter is an
  injection seam (defaults to the real `_Pyautogui` implementation);
  automated tests inject a fake and assert the real dispatch logic
  (which action maps to which call, with which arguments), never the
  live hardware effect.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Mapping, Optional, Sequence

from .errors import PathOutsideWorkspaceError, ShellCommandNotAllowedError, UnknownActionError

_SHELL_ACTIONS = ("run_shell",)
_FILE_ACTIONS = ("read_file", "write_file", "list_dir", "delete_file", "move_file")
_GUI_ACTIONS = ("move_mouse", "click", "type_text", "hotkey", "screenshot", "copy_to_clipboard", "paste_from_clipboard")


class _RealGUI:
    """The real, hardware-backed implementation -- never invoked by
    the automated test suite (see module docstring).
    """

    def screenshot(self):
        import pyautogui

        return pyautogui.screenshot()

    def move_mouse(self, x: int, y: int, *, duration: float = 0.0) -> None:
        import pyautogui

        pyautogui.moveTo(x, y, duration=duration)

    def click(self, *, x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> None:
        import pyautogui

        pyautogui.click(x=x, y=y, button=button)

    def type_text(self, text: str, *, interval: float = 0.0) -> None:
        import pyautogui

        pyautogui.typewrite(text, interval=interval)

    def hotkey(self, *keys: str) -> None:
        import pyautogui

        pyautogui.hotkey(*keys)

    def copy_to_clipboard(self, text: str) -> None:
        import pyperclip

        pyperclip.copy(text)

    def paste_from_clipboard(self) -> str:
        import pyperclip

        return pyperclip.paste()


class ComputerControlExecutor:
    def __init__(
        self, *, workspace_root: str, allowed_shell_commands: Sequence[str] = (),
        shell_timeout_seconds: float = 30.0, max_output_chars: int = 20000, _gui: Optional[Any] = None,
    ) -> None:
        self._workspace_root = os.path.realpath(workspace_root)
        os.makedirs(self._workspace_root, exist_ok=True)
        self._allowed_shell_commands = frozenset(allowed_shell_commands)
        self._shell_timeout_seconds = shell_timeout_seconds
        self._max_output_chars = max_output_chars
        self._gui = _gui if _gui is not None else _RealGUI()

    def _resolve_in_workspace(self, relative_path: str) -> str:
        candidate = os.path.realpath(os.path.join(self._workspace_root, relative_path))
        if candidate != self._workspace_root and not candidate.startswith(self._workspace_root + os.sep):
            raise PathOutsideWorkspaceError(
                f"path {relative_path!r} resolves outside the configured workspace root "
                f"({self._workspace_root!r}) -- refusing, this is a real path-traversal guard, not advisory"
            )
        return candidate

    def __call__(self, action: str, parameters: Mapping[str, Any]) -> Any:
        if action in _SHELL_ACTIONS:
            return self._run_shell(parameters)
        if action in _FILE_ACTIONS:
            return self._file_action(action, parameters)
        if action in _GUI_ACTIONS:
            return self._gui_action(action, parameters)
        raise UnknownActionError(
            f"ComputerControlExecutor has no action {action!r} -- expected one of "
            f"{_SHELL_ACTIONS + _FILE_ACTIONS + _GUI_ACTIONS}"
        )

    # -- Shell ---------------------------------------------------------

    def _run_shell(self, parameters: Mapping[str, Any]) -> Any:
        command = parameters["command"]
        program = command.strip().split()[0] if command.strip() else ""
        if not self._allowed_shell_commands or program not in self._allowed_shell_commands:
            raise ShellCommandNotAllowedError(
                f"shell command {command!r} (program {program!r}) is not in this executor's allowlist "
                f"{sorted(self._allowed_shell_commands)!r} -- fail closed, no default allowlist"
            )
        result = subprocess.run(
            command, shell=True, cwd=self._workspace_root, capture_output=True, text=True,
            timeout=parameters.get("timeout_seconds", self._shell_timeout_seconds),
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[: self._max_output_chars],
            "stderr": result.stderr[: self._max_output_chars],
        }

    # -- File operations -------------------------------------------------

    def _file_action(self, action: str, parameters: Mapping[str, Any]) -> Any:
        if action == "read_file":
            path = self._resolve_in_workspace(parameters["path"])
            with open(path, "r", encoding=parameters.get("encoding", "utf-8")) as f:
                return {"content": f.read()}
        if action == "write_file":
            path = self._resolve_in_workspace(parameters["path"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding=parameters.get("encoding", "utf-8")) as f:
                f.write(parameters["content"])
            return {"written": parameters["path"], "bytes": len(parameters["content"])}
        if action == "list_dir":
            path = self._resolve_in_workspace(parameters.get("path", "."))
            return {"entries": sorted(os.listdir(path))}
        if action == "delete_file":
            path = self._resolve_in_workspace(parameters["path"])
            os.remove(path)
            return {"deleted": parameters["path"]}
        if action == "move_file":
            src = self._resolve_in_workspace(parameters["src"])
            dst = self._resolve_in_workspace(parameters["dst"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
            return {"moved": {"src": parameters["src"], "dst": parameters["dst"]}}
        raise UnknownActionError(f"unhandled file action {action!r}")  # pragma: no cover

    # -- GUI -------------------------------------------------------------

    def _gui_action(self, action: str, parameters: Mapping[str, Any]) -> Any:
        if action == "screenshot":
            image = self._gui.screenshot()
            return {"image": image}
        if action == "move_mouse":
            self._gui.move_mouse(parameters["x"], parameters["y"], duration=parameters.get("duration", 0.0))
            return {"moved_to": (parameters["x"], parameters["y"])}
        if action == "click":
            self._gui.click(x=parameters.get("x"), y=parameters.get("y"), button=parameters.get("button", "left"))
            return {"clicked": {"x": parameters.get("x"), "y": parameters.get("y")}}
        if action == "type_text":
            self._gui.type_text(parameters["text"], interval=parameters.get("interval", 0.0))
            return {"typed_length": len(parameters["text"])}
        if action == "hotkey":
            self._gui.hotkey(*parameters["keys"])
            return {"hotkey": list(parameters["keys"])}
        if action == "copy_to_clipboard":
            self._gui.copy_to_clipboard(parameters["text"])
            return {"copied_length": len(parameters["text"])}
        if action == "paste_from_clipboard":
            return {"text": self._gui.paste_from_clipboard()}
        raise UnknownActionError(f"unhandled GUI action {action!r}")  # pragma: no cover
