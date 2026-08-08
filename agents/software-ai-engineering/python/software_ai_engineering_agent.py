"""Software & AI Engineering -- domain module for the
software-ai-engineering Chief Domain Agent.

Wires blueprint.json to real tools, guardrails, and quality gates. This
file is where domain logic lives; avishkar_agent itself never changes to
support this agent (agent-factory's Extension Model, README.md SS25).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from avishkar_agent import (
    AgentBlueprint,
    ChiefDomainAgent,
    Guardrail,
    InMemoryMemoryPolicy,
    MCPToolRef,
    QualityGate,
    Tool,
    ToolRegistry,
)
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_router import Router

_BLUEPRINT_PATH = Path(__file__).resolve().parent.parent / "blueprint.json"

# --- Tools -------------------------------------------------------------
# Small, real, deterministic implementations -- not stubs. Genuine static
# analysis engines belong to a future dedicated tool/MCP server; these
# are honestly scoped for what a Chief Domain Agent can call today.

_PRINT_PATTERN = re.compile(r"\bprint\(")
_BARE_EXCEPT_PATTERN = re.compile(r"\bexcept\s*:")
_CONTROL_FLOW_PATTERN = re.compile(r"\b(if|elif|for|while|except|and|or)\b")


def _static_check(code: str) -> List[str]:
    """Flags a small set of real, checkable code smells. Not a full
    linter -- see README.md Limitations.
    """
    issues = []
    if _PRINT_PATTERN.search(code):
        issues.append("print() found -- use structured logging instead (STANDARDS.md-equivalent for this codebase)")
    if _BARE_EXCEPT_PATTERN.search(code):
        issues.append("bare 'except:' found -- catch a specific exception type")
    if "TODO" in code or "FIXME" in code:
        issues.append("TODO/FIXME marker found -- resolve or file a tracked issue before merging")
    return issues


def _estimate_complexity(code: str) -> int:
    """A naive cyclomatic-complexity-style estimate: 1 (baseline path)
    plus one per control-flow keyword. Useful as a cheap signal for
    "does this function need splitting," not a certified metric.
    """
    return 1 + len(_CONTROL_FLOW_PATTERN.findall(code))


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool(name="static_check", call=_static_check, description="Flag simple, real code smells."))
    registry.register(
        Tool(
            name="estimate_complexity",
            call=_estimate_complexity,
            description="Naive cyclomatic-complexity-style estimate for a code snippet.",
        )
    )
    # Declared, not yet resolvable -- Phase 4 (mcp-factory) makes these
    # callable without any change here. See MCPToolRef in tools.py.
    registry.register(MCPToolRef(server="github", tool_name="get_file_contents"))
    registry.register(MCPToolRef(server="github", tool_name="create_pull_request"))
    return registry


# --- Guardrails ----------------------------------------------------------

_SECRET_PATTERN = re.compile(r"\b(password|api[_ ]?key|secret[_ ]?token|private[_ ]?key)\b", re.IGNORECASE)
_DESTRUCTIVE_PATTERN = re.compile(
    r"(rm\s+-rf|git\s+push\s+--force|drop\s+table|--no-verify)", re.IGNORECASE
)


def _no_secrets_in_task(task) -> Optional[str]:
    if _SECRET_PATTERN.search(task.input):
        return "task references a credential/secret directly -- route through a secrets manager, not the agent"
    return None


def _no_destructive_commands(task) -> Optional[str]:
    if _DESTRUCTIVE_PATTERN.search(task.input):
        return "task requests a destructive/irreversible command -- requires explicit human approval, not autonomous execution"
    return None


def _build_guardrails() -> tuple:
    return (
        Guardrail(name="no-secrets-in-task", check=_no_secrets_in_task),
        Guardrail(name="no-destructive-commands", check=_no_destructive_commands),
    )


# --- Quality gates ---------------------------------------------------------

_PLACEHOLDER_PATTERN = re.compile(r"(lorem ipsum|TODO|FIXME|\bTBD\b)", re.IGNORECASE)


def _minimum_substance(result) -> bool:
    return len(result.output.strip()) >= 10


def _no_placeholder_output(result) -> bool:
    return not _PLACEHOLDER_PATTERN.search(result.output)


def _build_quality_gates() -> tuple:
    return (
        QualityGate(name="minimum-substance", check=_minimum_substance),
        QualityGate(name="no-placeholder-output", check=_no_placeholder_output),
    )


# --- Construction -----------------------------------------------------------


def load_blueprint(model_override: Optional[str] = None) -> AgentBlueprint:
    blueprint = AgentBlueprint.from_file(_BLUEPRINT_PATH)
    if model_override is None:
        return blueprint
    # AgentBlueprint is frozen -- rebuild with the override rather than
    # mutate, so tests/examples can point this agent at a MockProvider
    # model_id without editing the committed blueprint.json.
    import dataclasses

    return dataclasses.replace(blueprint, default_model=model_override)


def build_software_ai_engineering_agent(router: Router, *, model_override: Optional[str] = None) -> ChiefDomainAgent:
    """Construct the Software & AI Engineering Chief Domain Agent.

    `model_override` lets callers (tests, the example) point this agent
    at whatever model_id the given Router actually has registered,
    without editing the committed blueprint.json (which names
    'claude-opus-5', the real default for production use).
    """
    blueprint = load_blueprint(model_override)
    return ChiefDomainAgent(
        blueprint=blueprint,
        router=router,
        memory=InMemoryMemoryPolicy(),
        tools=_build_tool_registry(),
        thinking_models=DEFAULT_THINKING_MODELS,
        guardrails=_build_guardrails(),
        quality_gates=_build_quality_gates(),
    )
