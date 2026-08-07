import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from avishkar_core import ConfigError, load_config


class TestConfigLayering(unittest.TestCase):
    def test_defaults_only(self):
        config = load_config(defaults={"router": {"timeout": 30}})
        self.assertEqual(config.get("router.timeout"), 30)

    def test_missing_key_returns_default_arg(self):
        config = load_config(defaults={"a": 1})
        self.assertIsNone(config.get("nonexistent"))
        self.assertEqual(config.get("nonexistent", "fallback"), "fallback")

    def test_require_raises_on_missing_key(self):
        config = load_config(defaults={"a": 1})
        with self.assertRaises(ConfigError):
            config.require("b")

    def test_require_returns_present_key(self):
        config = load_config(defaults={"a": {"b": 42}})
        self.assertEqual(config.require("a.b"), 42)

    def test_file_layer_overrides_defaults(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"router": {"timeout": 60}}, f)
            path = f.name
        try:
            config = load_config(defaults={"router": {"timeout": 30, "retries": 3}}, config_path=path)
            self.assertEqual(config.get("router.timeout"), 60)
            self.assertEqual(config.get("router.retries"), 3)  # not overridden, survives deep-merge
        finally:
            os.unlink(path)

    def test_missing_config_file_raises(self):
        with self.assertRaises(ConfigError):
            load_config(config_path="/nonexistent/path/does-not-exist.json")

    def test_malformed_config_file_raises(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{not valid json")
            path = f.name
        try:
            with self.assertRaises(ConfigError):
                load_config(config_path=path)
        finally:
            os.unlink(path)

    def test_env_layer_overrides_file_and_defaults(self):
        with patch.dict(os.environ, {"AVISHKAR_ROUTER__TIMEOUT": "90"}, clear=False):
            config = load_config(defaults={"router": {"timeout": 30}})
            self.assertEqual(config.get("router.timeout"), 90)

    def test_env_layer_json_coercion(self):
        env = {
            "AVISHKAR_FEATURE__ENABLED": "true",
            "AVISHKAR_FEATURE__RETRIES": "5",
            "AVISHKAR_FEATURE__TAGS": '["a", "b"]',
            "AVISHKAR_FEATURE__NAME": "plain-string",
        }
        with patch.dict(os.environ, env, clear=False):
            config = load_config()
            self.assertIs(config.get("feature.enabled"), True)
            self.assertEqual(config.get("feature.retries"), 5)
            # Arrays come back as immutable tuples, not lists -- see
            # CONTRACT.md SS1: a resolved Config never exposes a mutable
            # reference into its own state.
            self.assertEqual(config.get("feature.tags"), ("a", "b"))
            self.assertEqual(config.get("feature.name"), "plain-string")

    def test_overrides_win_over_everything(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"router": {"timeout": 60}}, f)
            path = f.name
        env = {"AVISHKAR_ROUTER__TIMEOUT": "90"}
        try:
            with patch.dict(os.environ, env, clear=False):
                config = load_config(
                    defaults={"router": {"timeout": 30}},
                    config_path=path,
                    overrides={"router": {"timeout": 120}},
                )
                self.assertEqual(config.get("router.timeout"), 120)
        finally:
            os.unlink(path)

    def test_deep_merge_preserves_sibling_keys(self):
        config = load_config(
            defaults={"router": {"timeout": 30, "retries": 3}},
            overrides={"router": {"timeout": 60}},
        )
        self.assertEqual(config.get("router.timeout"), 60)
        self.assertEqual(config.get("router.retries"), 3)

    def test_list_values_replaced_not_merged(self):
        config = load_config(
            defaults={"router": {"models": ["a", "b"]}},
            overrides={"router": {"models": ["c"]}},
        )
        self.assertEqual(config.get("router.models"), ("c",))


class TestConfigValidation(unittest.TestCase):
    def test_reserved_key_prefix_rejected(self):
        with self.assertRaises(ConfigError):
            load_config(defaults={"__internal": 1})

    def test_non_dict_document_rejected(self):
        with self.assertRaises(ConfigError):
            load_config(defaults={"a": [1, 2, {"__bad": 1}]})

    def test_unsupported_value_type_rejected(self):
        class NotJsonSerializable:
            pass

        with self.assertRaises(ConfigError):
            load_config(defaults={"a": NotJsonSerializable()})


class TestConfigImmutability(unittest.TestCase):
    def test_as_dict_is_a_disconnected_snapshot(self):
        config = load_config(defaults={"a": {"b": 1}})
        snapshot = config.as_dict()
        snapshot["a"]["b"] = 999
        self.assertEqual(config.get("a.b"), 1)

    def test_resolved_config_has_no_public_setter(self):
        config = load_config(defaults={"a": 1})
        self.assertFalse(hasattr(config, "set"))
        self.assertFalse(hasattr(config, "__setitem__"))


if __name__ == "__main__":
    unittest.main()
