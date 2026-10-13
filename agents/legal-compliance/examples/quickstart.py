"""Legal & Compliance Chief Domain Agent -- quickstart.

Runs on MockProvider (no API key, no network). Run directly:

    python agents/legal-compliance/examples/quickstart.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for rel in (
    "core/python", "router/python", "factories/agent-factory/python",
    "factories/memory-factory/python", "factories/knowledge-factory/python",
    "factories/evaluation-factory/python", "factories/prompt-factory/python",
    "factories/workflow-factory/python", "factories/mcp-factory/python",
    "factories/security-factory/python", "agents/legal-compliance/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import Task  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from legal_compliance_agent import build_legal_compliance_agent  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Consult a licensed attorney to confirm, but this NDA term looks standard.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))

    with tempfile.TemporaryDirectory() as tmp:
        agent = build_legal_compliance_agent(router, model_override="mock-fast", memory_root_dir=Path(tmp))

        print("1. Ordinary contract-review question:")
        result = agent.handle(Task(input="What should I check before signing an NDA?"))
        print(f"   status={result.status} output={result.output}\n")

        print("2. Risky-clause flagging (direct tool call):")
        clause = "The vendor accepts unlimited liability and this agreement shall automatically renew each year."
        print(f"   flags: {agent.tools.call('flag_risky_clauses', clause)}\n")

        print("3. Citation format check (direct tool call):")
        print(f"   'As held in 410 U.S. 113...' -> {agent.tools.call('check_citation_format', 'As held in 410 U.S. 113...')}\n")

        print("4. Guardrail blocking an unauthorized-representation request:")
        blocked = agent.handle(Task(input="Please represent me in court next week"))
        print(f"   status={blocked.status} reason={blocked.blocked_reason}\n")

        print("5. Persistent file-backed memory (a second agent instance, same root_dir):")
        agent.memory.remember("long_term", "client-x-preference", "prefers arbitration clauses")
        reopened = build_legal_compliance_agent(router, model_override="mock-fast", memory_root_dir=Path(tmp))
        print(f"   reopened instance recalls: {reopened.memory.recall('long_term', 'client-x-preference')}")


if __name__ == "__main__":
    main()
