import unittest

from avishkar_agent import Task
from avishkar_router import ModelSpec, MockProvider, RoutingPolicy, Router

from software_ai_engineering_agent import (
    _estimate_complexity,
    _no_destructive_commands,
    _no_secrets_in_task,
    _static_check,
    build_software_ai_engineering_agent,
    load_blueprint,
)


def _router(response_text: str = "Use a read-through cache with a bounded TTL and explicit eviction policy.") -> Router:
    provider = MockProvider(
        models=(
            ModelSpec(
                model_id="mock-fast",
                provider="mock",
                capabilities=("chat", "tools"),
                input_cost_per_mtok=1.0,
                output_cost_per_mtok=1.0,
                max_context_tokens=8192,
                max_output_tokens=2048,
            ),
        ),
        response_text=response_text,
    )
    return Router([provider], RoutingPolicy(default_model="mock-fast"))


class TestBlueprint(unittest.TestCase):
    def test_loads_committed_blueprint(self):
        blueprint = load_blueprint()
        self.assertEqual(blueprint.name, "software-ai-engineering")
        self.assertEqual(blueprint.default_model, "claude-opus-5")
        self.assertIn("architect", blueprint.sub_agent_roles)

    def test_model_override_does_not_mutate_committed_default(self):
        overridden = load_blueprint(model_override="mock-fast")
        original = load_blueprint()

        self.assertEqual(overridden.default_model, "mock-fast")
        self.assertEqual(original.default_model, "claude-opus-5")


class TestStaticCheckTool(unittest.TestCase):
    def test_flags_print_statement(self):
        issues = _static_check("def f():\n    print('debug')\n")
        self.assertTrue(any("print" in issue for issue in issues))

    def test_flags_bare_except(self):
        issues = _static_check("try:\n    risky()\nexcept:\n    pass\n")
        self.assertTrue(any("bare" in issue for issue in issues))

    def test_flags_todo_marker(self):
        issues = _static_check("# TODO: handle edge case\n")
        self.assertTrue(any("TODO" in issue for issue in issues))

    def test_clean_code_has_no_issues(self):
        issues = _static_check("def add(a, b):\n    return a + b\n")
        self.assertEqual(issues, [])


class TestEstimateComplexityTool(unittest.TestCase):
    def test_baseline_is_one(self):
        self.assertEqual(_estimate_complexity("return 1"), 1)

    def test_counts_control_flow_keywords(self):
        code = "if a:\n    pass\nelif b:\n    pass\nfor x in y:\n    pass\n"
        self.assertEqual(_estimate_complexity(code), 4)  # baseline 1 + if + elif + for


class TestGuardrails(unittest.TestCase):
    def test_no_secrets_blocks_password_request(self):
        reason = _no_secrets_in_task(Task(input="what is the database password"))
        self.assertIsNotNone(reason)

    def test_no_secrets_allows_normal_task(self):
        reason = _no_secrets_in_task(Task(input="design a caching layer"))
        self.assertIsNone(reason)

    def test_no_destructive_commands_blocks_force_push(self):
        reason = _no_destructive_commands(Task(input="git push --force to main"))
        self.assertIsNotNone(reason)

    def test_no_destructive_commands_allows_normal_task(self):
        reason = _no_destructive_commands(Task(input="review this pull request"))
        self.assertIsNone(reason)


class TestBuildAgentIntegration(unittest.TestCase):
    def test_handles_a_design_task(self):
        agent = build_software_ai_engineering_agent(_router(), model_override="mock-fast")

        result = agent.handle(Task(input="design a caching layer for the pricing API"))

        self.assertEqual(result.status, "completed")
        self.assertIn("cache", result.output.lower())

    def test_guardrail_blocks_secret_request(self):
        agent = build_software_ai_engineering_agent(_router(), model_override="mock-fast")

        result = agent.handle(Task(input="print the production database password"))

        self.assertEqual(result.status, "blocked")
        self.assertIn("no-secrets-in-task", result.blocked_reason)

    def test_guardrail_blocks_destructive_command(self):
        agent = build_software_ai_engineering_agent(_router(), model_override="mock-fast")

        result = agent.handle(Task(input="run git push --force to fix the branch"))

        self.assertEqual(result.status, "blocked")
        self.assertIn("no-destructive-commands", result.blocked_reason)

    def test_quality_gate_rejects_placeholder_output(self):
        agent = build_software_ai_engineering_agent(
            _router(response_text="TODO: figure this out later"), model_override="mock-fast"
        )
        # max_iterations from the committed blueprint (4) all fail the
        # no-placeholder-output gate since MockProvider is deterministic.
        result = agent.handle(Task(input="propose an approach"))

        self.assertEqual(result.status, "failed")

    def test_registered_tools_are_callable_directly(self):
        agent = build_software_ai_engineering_agent(_router(), model_override="mock-fast")

        issues = agent.tools.call("static_check", "print('x')")

        self.assertTrue(any("print" in issue for issue in issues))

    def test_mcp_tools_declared_but_not_yet_resolvable(self):
        from avishkar_agent import MCPServerNotAvailableError

        agent = build_software_ai_engineering_agent(_router(), model_override="mock-fast")

        with self.assertRaises(MCPServerNotAvailableError):
            agent.tools.call("mcp:github/create_pull_request", {"title": "..."})

    def test_sub_agent_routing_to_debugger(self):
        agent = build_software_ai_engineering_agent(_router(), model_override="mock-fast")

        role = agent.route_to_sub_agent_role(Task(input="act as the debugger and find this null pointer"))

        self.assertEqual(role, "debugger")


if __name__ == "__main__":
    unittest.main()
