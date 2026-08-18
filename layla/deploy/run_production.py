"""Real, runnable production entrypoint -- Mission Layla Directive D,
Part XVII (Production Deployment). See CONTRACT.md SS60.

This wires exactly the same real components every other part of this
platform already uses -- `ExecutiveRuntime`, `Orchestrator`,
`ChiefDomainAgent`, `Router`, `FileMemoryPolicy`, `HealthServer`,
`install_graceful_shutdown` -- never a new orchestration path. It is
deliberately generic (one "general-agent" domain): the actual
production agent roster (which Chief Domain Agents, which tools, which
capability domains) is application-specific and is not decided by this
platform layer -- see `layla/README.md`'s Extension Model. Treat this
script as a real, working reference/smoke-test entrypoint, not the
definitive production topology.

Configuration is environment-variable-driven, layered on top of the
platform's own real `avishkar_core.Config` precedence (defaults < file
< env < overrides) rather than inventing a second config system:

    ANTHROPIC_API_KEY      real credential for avishkar_router's real
                            AnthropicProvider. If unset, this script
                            logs a loud warning and falls back to
                            MockProvider -- clearly NOT a real
                            production configuration, but still a real,
                            runnable process (useful for smoke-testing
                            the deployment boundary itself: health
                            server, graceful shutdown, data directory
                            wiring -- all real regardless of which
                            provider backs the agent).
    LAYLA_DEFAULT_MODEL     default: claude-haiku-4-5 (cheapest real
                            model in the catalog -- see
                            docs/live-integration-guide.md).
    LAYLA_DATA_DIR          default: /data/layla -- FileMemoryPolicy's
                            real on-disk root, meant to be a mounted
                            volume so task/session/audit state survives
                            container restarts. See OPERATIONS.md for
                            backup/restore procedure
                            (avishkar_layla.deployment.backup_data_directory).
    LAYLA_HEALTH_HOST       default: 0.0.0.0
    LAYLA_HEALTH_PORT       default: 8080
    LAYLA_LOG_LEVEL         default: INFO
"""

from __future__ import annotations

import logging
import os

from avishkar_agent import AgentBlueprint, ChiefDomainAgent, InMemoryMemoryPolicy, Orchestrator, ToolRegistry
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS
from avishkar_memory.backends.file_backend import FileMemoryPolicy
from avishkar_router import ModelSpec, MockProvider, Router, RoutingPolicy

from avishkar_layla import ExecutiveRuntime, HealthServer, LaylaMemoryPolicy, install_graceful_shutdown

_LOG = logging.getLogger("avishkar_layla.deploy")


def _build_router() -> tuple[Router, bool, str]:
    """Real Router construction. Returns (router, is_real_llm,
    default_model_id) so the caller can log an honest, unambiguous
    startup message and give the agent blueprint the same default
    model id the RoutingPolicy actually uses.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        model_id = os.environ.get("LAYLA_DEFAULT_MODEL", "claude-haiku-4-5")
        from avishkar_router.providers.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider(api_key=api_key)
        return Router([provider], RoutingPolicy(default_model=model_id)), True, model_id

    _LOG.warning(
        "ANTHROPIC_API_KEY is not set -- falling back to MockProvider. "
        "This process will run for real (real HealthServer, real "
        "graceful shutdown, real FileMemoryPolicy durability) but every "
        "agent response is a fixed mock string. Set ANTHROPIC_API_KEY "
        "before treating this as a real production deployment."
    )
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="[MockProvider active -- set ANTHROPIC_API_KEY for real responses]",
    )
    return Router([provider], RoutingPolicy(default_model="mock-fast")), False, "mock-fast"


def build_runtime() -> tuple[ExecutiveRuntime, bool]:
    router, is_real_llm, default_model = _build_router()
    blueprint = AgentBlueprint(
        name="general-agent", domain="General", version="0.1.0",
        mission="General-purpose reference agent for the production deployment boundary.",
        default_model=default_model,
    )
    agent = ChiefDomainAgent(blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS)
    orchestrator = Orchestrator([agent])

    data_dir = os.environ.get("LAYLA_DATA_DIR", "/data/layla")
    memory = LaylaMemoryPolicy(FileMemoryPolicy(data_dir))

    runtime = ExecutiveRuntime(orchestrator=orchestrator, agent_domains={"general-agent": "General"}, memory=memory)
    return runtime, is_real_llm


def main() -> None:
    logging.basicConfig(level=os.environ.get("LAYLA_LOG_LEVEL", "INFO"))
    runtime, is_real_llm = build_runtime()

    health_host = os.environ.get("LAYLA_HEALTH_HOST", "0.0.0.0")
    health_port = int(os.environ.get("LAYLA_HEALTH_PORT", "8080"))
    server = HealthServer(runtime, host=health_host, port=health_port)
    server.start()

    install_graceful_shutdown(runtime)

    _LOG.info(
        "Layla production runtime started (real_llm=%s, data_dir=%s, health=http://%s:%s/health)",
        is_real_llm, os.environ.get("LAYLA_DATA_DIR", "/data/layla"), health_host, server.port,
    )
    try:
        runtime.run_forever()
    finally:
        _LOG.info("Layla production runtime shutting down")
        server.stop()


if __name__ == "__main__":
    main()
