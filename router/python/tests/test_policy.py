import unittest

from avishkar_router import CompletionRequest, Message, RoutingPolicy, RoutingRule


def _req(**kwargs) -> CompletionRequest:
    kwargs.setdefault("messages", (Message(role="user", content="hi"),))
    return CompletionRequest(**kwargs)


class TestRoutingPolicySelection(unittest.TestCase):
    def test_explicit_model_skips_rules_and_default(self):
        policy = RoutingPolicy(
            default_model="default-model",
            rules=(RoutingRule(models=("rule-model",), capabilities=()),),
        )
        candidates = policy.select_candidates(_req(model="explicit-model"))
        self.assertEqual(candidates, ("explicit-model",))

    def test_no_match_falls_back_to_default(self):
        policy = RoutingPolicy(default_model="default-model", rules=())
        candidates = policy.select_candidates(_req())
        self.assertEqual(candidates, ("default-model",))

    def test_task_type_rule_matches(self):
        policy = RoutingPolicy(
            default_model="default-model",
            rules=(RoutingRule(models=("cheap-a", "cheap-b"), task_type="cheap"),),
        )
        candidates = policy.select_candidates(_req(task_type="cheap"))
        self.assertEqual(candidates, ("cheap-a", "cheap-b"))

    def test_task_type_rule_does_not_match_different_task(self):
        policy = RoutingPolicy(
            default_model="default-model",
            rules=(RoutingRule(models=("cheap-a",), task_type="cheap"),),
        )
        candidates = policy.select_candidates(_req(task_type="fast"))
        self.assertEqual(candidates, ("default-model",))

    def test_capability_rule_requires_subset(self):
        policy = RoutingPolicy(
            default_model="default-model",
            rules=(RoutingRule(models=("vision-model",), capabilities=("vision",)),),
        )
        matching = policy.select_candidates(_req(capabilities=("vision", "tools")))
        self.assertEqual(matching, ("vision-model",))

        not_matching = policy.select_candidates(_req(capabilities=("tools",)))
        self.assertEqual(not_matching, ("default-model",))

    def test_first_matching_rule_wins(self):
        policy = RoutingPolicy(
            default_model="default-model",
            rules=(
                RoutingRule(models=("first",), capabilities=()),
                RoutingRule(models=("second",), capabilities=()),
            ),
        )
        candidates = policy.select_candidates(_req())
        self.assertEqual(candidates, ("first",))


class TestRoutingPolicyFromConfig(unittest.TestCase):
    def test_builds_from_config_document(self):
        from avishkar_core import load_config

        config = load_config(
            defaults={
                "router": {
                    "default_model": "claude-opus-5",
                    "rules": [
                        {"task_type": "cheap", "models": ["claude-haiku-4-5"]},
                        {"capabilities": ["vision"], "models": ["claude-opus-5"]},
                    ],
                }
            }
        )
        policy = RoutingPolicy.from_config(config)

        self.assertEqual(policy.default_model, "claude-opus-5")
        self.assertEqual(len(policy.rules), 2)
        self.assertEqual(policy.rules[0].task_type, "cheap")
        self.assertEqual(policy.rules[0].models, ("claude-haiku-4-5",))
        self.assertEqual(policy.rules[1].capabilities, ("vision",))

    def test_missing_default_model_raises(self):
        from avishkar_core import ConfigError, load_config

        config = load_config(defaults={"router": {}})
        with self.assertRaises(ConfigError):
            RoutingPolicy.from_config(config)


if __name__ == "__main__":
    unittest.main()
