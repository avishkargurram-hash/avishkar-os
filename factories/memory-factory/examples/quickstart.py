"""Memory Framework -- quickstart.

Demonstrates FileMemoryPolicy and SQLiteMemoryPolicy, then closes the
Agent Framework seam: building a real ChiefDomainAgent whose
`blueprint.json` names a persistent backend, resolved via
build_memory_policy(). Run directly:

    python factories/memory-factory/examples/quickstart.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT / "core" / "python"))
sys.path.insert(0, str(_ROOT / "router" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "agent-factory" / "python"))
sys.path.insert(0, str(_ROOT / "factories" / "memory-factory" / "python"))

from avishkar_agent import AgentBlueprint, ChiefDomainAgent, MemoryPolicyConfig, Task, ToolRegistry  # noqa: E402
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from avishkar_memory import FileMemoryPolicy, SQLiteMemoryPolicy, build_memory_policy  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        print("1. FileMemoryPolicy -- durable across process restarts:")
        file_memory = FileMemoryPolicy(Path(tmp))
        file_memory.remember("long_term", "preferred_stack", "Python + stdlib-first")
        reopened = FileMemoryPolicy(Path(tmp))  # a fresh instance, same directory
        print(f"   reopened instance recalls: {reopened.recall('long_term', 'preferred_stack')}\n")

        print("2. SQLiteMemoryPolicy -- one table, four kinds:")
        sqlite_memory = SQLiteMemoryPolicy(":memory:")
        sqlite_memory.remember("episodic", "incident-42", {"summary": "cache stampede at 14:03"})
        print(f"   recall: {sqlite_memory.recall('episodic', 'incident-42')}\n")

        print("3. build_memory_policy() resolves a blueprint's declared backend:")
        blueprint = AgentBlueprint(
            name="demo-agent", domain="Demo", version="0.1.0",
            mission="Answer demo questions with durable memory.",
            default_model="mock-fast",
            memory_policy=MemoryPolicyConfig(backend="sqlite"),
        )
        memory = build_memory_policy(blueprint.memory_policy)
        print(f"   backend='{blueprint.memory_policy.backend}' -> {type(memory).__name__}\n")

        print("4. A real ChiefDomainAgent using a persistent backend end to end:")
        provider = MockProvider(
            models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                               input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                               max_context_tokens=8192, max_output_tokens=2048),),
            response_text="Noted -- I'll remember that for next time.",
        )
        router = Router([provider], RoutingPolicy(default_model="mock-fast"))
        agent = ChiefDomainAgent(blueprint, router, memory, ToolRegistry(), DEFAULT_THINKING_MODELS)
        result = agent.handle(Task(input="Remember that our deploys happen on Fridays."))
        memory.remember("semantic", "deploy_day", "Friday")
        print(f"   agent status={result.status}")
        print(f"   memory now recalls deploy_day={memory.recall('semantic', 'deploy_day')}")


if __name__ == "__main__":
    main()
