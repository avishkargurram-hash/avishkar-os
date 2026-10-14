"""Security Framework -- quickstart.

Demonstrates secret scanning/redaction, a real ChiefDomainAgent
protected by secret-scanning and rate-limit guardrails, a checklist
review, and -- the "retroactive review of everything built above"
responsibility -- an actual scan of this entire repository for
committed secrets. Run directly:

    python factories/security-factory/examples/quickstart.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
for rel in ("core/python", "router/python", "factories/agent-factory/python", "factories/security-factory/python"):
    sys.path.insert(0, str(_ROOT / rel))

from avishkar_agent import AgentBlueprint, ChiefDomainAgent, InMemoryMemoryPolicy, Task, ToolRegistry  # noqa: E402
from avishkar_agent.thinking import DEFAULT_THINKING_MODELS  # noqa: E402
from avishkar_router import ModelSpec, MockProvider, Router, RoutingPolicy  # noqa: E402

from avishkar_security import (  # noqa: E402
    SECURITY_CHECKLIST,
    make_rate_limit_guardrail,
    make_secret_scanning_guardrail,
    redact_secrets,
    run_checklist,
    scan_repository_for_secrets,
)


def main() -> None:
    print("1. Scanning and redacting a secret-shaped string:")
    leaked = "Here's my key: AKIAIOSFODNN7EXAMPLE -- don't share it."
    print(f"   original: {leaked}")
    print(f"   redacted: {redact_secrets(leaked)}\n")

    print("2. A real ChiefDomainAgent protected by two real guardrails:")
    blueprint = AgentBlueprint(
        name="support-agent", domain="Support", version="0.1.0",
        mission="Answer support questions.", default_model="mock-fast",
    )
    provider = MockProvider(
        models=(ModelSpec(model_id="mock-fast", provider="mock", capabilities=("chat",),
                           input_cost_per_mtok=0.0, output_cost_per_mtok=0.0,
                           max_context_tokens=8192, max_output_tokens=2048),),
        response_text="Here's the answer.",
    )
    router = Router([provider], RoutingPolicy(default_model="mock-fast"))
    agent = ChiefDomainAgent(
        blueprint, router, InMemoryMemoryPolicy(), ToolRegistry(), DEFAULT_THINKING_MODELS,
        guardrails=(
            make_secret_scanning_guardrail(),
            make_rate_limit_guardrail("rl", max_calls=2, window_seconds=60),
        ),
    )
    ok_result = agent.handle(Task(input="What's our refund policy?"))
    blocked_result = agent.handle(Task(input="My AWS key is AKIAIOSFODNN7EXAMPLE, is that right?"))
    print(f"   ordinary question: status={ok_result.status}")
    print(f"   question containing a secret: status={blocked_result.status} reason={blocked_result.blocked_reason}\n")

    print("3. A checklist review:")
    answers = {item.id: True for item in SECURITY_CHECKLIST}
    answers["rate-limiting"] = False
    report = run_checklist("support-agent", answers, notes={"rate-limiting": "not yet configured for the real model provider"})
    print(f"   subject={report.subject} passed={report.passed}")
    for failing in report.failing:
        print(f"   FAILING: {failing.item_id} -- {failing.note}")
    print()

    print("4. Retroactive review: scanning this repository for committed secrets:")
    findings = scan_repository_for_secrets(_ROOT)
    own_fixtures_dir = str(Path("factories") / "security-factory" / "python" / "tests")
    known_fixtures = [f for f in findings if own_fixtures_dir in str(f.path)]
    real_findings = [f for f in findings if f not in known_fixtures]

    print(f"   scanned {_ROOT}")
    print(f"   total pattern matches: {len(findings)}")
    print(f"   of which inside this framework's own test fixtures (deliberately fake, proving detection works): {len(known_fixtures)}")
    print(f"   findings outside test fixtures: {len(real_findings)}")
    for finding in real_findings:
        print(f"   - {finding.path.relative_to(_ROOT)}: {finding.match.pattern_name} ({finding.match.preview})")
    if not real_findings:
        print("   (none -- the platform's own source has no committed secrets as of this run)")
    elif all(f.path.name == "quickstart.py" and "security-factory" in str(f.path) for f in real_findings):
        print(
            "   ^ these are step 1's own demo string above (AWS's public\n"
            "     documentation placeholder, AKIAIOSFODNN7EXAMPLE) -- correctly\n"
            "     detected, not a real leak. No other findings in the repo."
        )


if __name__ == "__main__":
    main()
