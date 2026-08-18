"""Real executors for `EmbodimentController.register_executor()` --
Mission Layla Directive D, Part III (Computer Control) and Part IV
(Android/ADB). See CONTRACT.md SS34.

Every executor here is a plain callable `(action, parameters) ->
output` -- exactly `embodiment.EmbodimentExecutor`'s shape. None of
them perform their own risk/approval check: `EmbodimentController.request()`
already computes risk and enforces `ApprovalManager` BEFORE any
executor is looked up or called (embodiment.py), and
EMBODIMENT_COMPUTER_CONTROL/EMBODIMENT_ADB are both in that module's
`_DEFAULT_HIGH_RISK_CAPABILITIES` -- every action through these
executors always requires approval, structurally, regardless of what
the action's text happens to classify as. Directive D Part III,
verbatim: "Never give arbitrary unrestricted computer control to an
LLM." This package is what runs only AFTER that gate has already been
cleared.
"""

from __future__ import annotations

from .adb_executor import ADBExecutor, is_adb_available
from .browser_executor import BrowserExecutor
from .computer_control_executor import ComputerControlExecutor
from .errors import (
    ADBNotAvailableError,
    BrowserActionError,
    PathOutsideWorkspaceError,
    ShellCommandNotAllowedError,
    UnknownActionError,
)
from .home_assistant_executor import HomeAssistantExecutor, HomeAssistantNotConfiguredError

__all__ = [
    "ADBExecutor",
    "ADBNotAvailableError",
    "BrowserActionError",
    "BrowserExecutor",
    "ComputerControlExecutor",
    "HomeAssistantExecutor",
    "HomeAssistantNotConfiguredError",
    "PathOutsideWorkspaceError",
    "ShellCommandNotAllowedError",
    "UnknownActionError",
    "is_adb_available",
]
