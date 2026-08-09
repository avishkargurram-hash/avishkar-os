"""Cross-domain review workflow -- quickstart.

Runs the real legal-compliance and finance-economics Chief Domain
Agents (Phase 13) through this shelf's cross-domain-review workflow --
genuine multi-agent composition, not a toy example. Run directly:

    python workflows/cross-domain-review/examples/quickstart.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for rel in (
    "core/python", "router/python", "factories/agent-factory/python",
    "factories/mcp-factory/python", "factories/knowledge-factory/python",
    "factories/memory-factory/python", "factories/workflow-factory/python",
    "factories/evaluation-factory/python", "factories/prompt-factory/python",
    "factories/security-factory/python",
    "agents/legal-compliance/python", "agents/finance-economics/python",
    "workflows/cross-domain-review/python",
):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router  # noqa: E402

from cross_domain_review_workflow import run_cross_domain_review  # noqa: E402
from finance_economics_agent import build_finance_economics_agent  # noqa: E402
from legal_compliance_agent import build_legal_compliance_agent  # noqa: E402


def main() -> None:
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat", "tools"),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Consult the appropriate professional to confirm before proceeding.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))

    with tempfile.TemporaryDirectory() as tmp:
        legal = build_legal_compliance_agent(router, model_override="mock-fast", memory_root_dir=Path(tmp))
        finance = build_finance_economics_agent(router, model_override="mock-fast", memory_root_dir=Path(tmp))

        result = run_cross_domain_review(
            legal, finance, "We're considering a new vendor contract with a $500K annual commitment."
        )

        print(f"Workflow status: {result.status}")
        print(f"Steps run: {' -> '.join(result.history)}\n")
        print("Combined summary:")
        print(result.state["summary"])


if __name__ == "__main__":
    main()
