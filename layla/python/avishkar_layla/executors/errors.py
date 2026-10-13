"""Errors for the executors package. See CONTRACT.md SS34."""

from __future__ import annotations

from ..errors import LaylaError


class UnknownActionError(LaylaError):
    """An executor was called with an `action` it doesn't implement."""


class BrowserActionError(LaylaError):
    """A real Playwright browser action failed (navigation timeout,
    selector not found, page crashed)."""


class ShellCommandNotAllowedError(LaylaError):
    """A `run_shell` action's command was not in the executor's
    configured allowlist -- fail closed, no default allowlist.
    """


class PathOutsideWorkspaceError(LaylaError):
    """A file-operation action's path resolved (after following `..`/
    symlinks) outside the executor's configured workspace root.
    """


class ADBNotAvailableError(LaylaError):
    """The `adb` binary is not installed/discoverable, or no device is
    connected -- the documented ADAPTER READY boundary.
    """
