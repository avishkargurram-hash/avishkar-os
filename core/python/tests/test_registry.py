import unittest

from avishkar_core import (
    DependencyDirectionError,
    EventBus,
    InvalidManifestError,
    ModuleAlreadyRegisteredError,
    ModuleManifest,
    ModuleNotRegisteredError,
    ModuleRegistry,
)


def _manifest(name="agent-factory", kind="framework", **kwargs) -> ModuleManifest:
    return ModuleManifest(name=name, version="0.1.0", kind=kind, **kwargs)


class TestModuleManifestValidation(unittest.TestCase):
    def test_valid_manifest_constructs(self):
        manifest = _manifest()
        self.assertEqual(manifest.name, "agent-factory")
        self.assertEqual(manifest.dependencies, ("core",))

    def test_non_kebab_case_name_rejected(self):
        with self.assertRaises(InvalidManifestError):
            _manifest(name="Agent_Factory")

    def test_non_semver_version_rejected(self):
        with self.assertRaises(InvalidManifestError):
            ModuleManifest(name="agent-factory", version="v1", kind="framework")

    def test_invalid_kind_rejected(self):
        with self.assertRaises(InvalidManifestError):
            _manifest(kind="not-a-real-kind")


class TestModuleRegistryRegistration(unittest.TestCase):
    def test_register_then_get(self):
        registry = ModuleRegistry()
        manifest = _manifest()
        registry.register(manifest, instance="the-instance")

        registered = registry.get("agent-factory")
        self.assertEqual(registered.manifest, manifest)
        self.assertEqual(registered.instance, "the-instance")

    def test_get_unknown_module_raises(self):
        registry = ModuleRegistry()
        with self.assertRaises(ModuleNotRegisteredError):
            registry.get("nonexistent")

    def test_duplicate_registration_raises_without_replace(self):
        registry = ModuleRegistry()
        registry.register(_manifest())
        with self.assertRaises(ModuleAlreadyRegisteredError):
            registry.register(_manifest())

    def test_duplicate_registration_allowed_with_replace(self):
        registry = ModuleRegistry()
        registry.register(_manifest(), instance="v1")
        registry.register(_manifest(), instance="v2", replace=True)
        self.assertEqual(registry.get("agent-factory").instance, "v2")

    def test_app_dependency_rejected(self):
        registry = ModuleRegistry()
        manifest = _manifest(dependencies=("app:tryvanta",))
        with self.assertRaises(DependencyDirectionError):
            registry.register(manifest)

    def test_list_returns_registration_order(self):
        registry = ModuleRegistry()
        registry.register(_manifest(name="a-factory"))
        registry.register(_manifest(name="b-factory"))
        registry.register(_manifest(name="c-factory"))

        names = [m.manifest.name for m in registry.list()]
        self.assertEqual(names, ["a-factory", "b-factory", "c-factory"])

    def test_list_filters_by_kind(self):
        registry = ModuleRegistry()
        registry.register(_manifest(name="a-factory", kind="framework"))
        registry.register(_manifest(name="software-ai-engineering", kind="agent"))

        agents = [m.manifest.name for m in registry.list(kind="agent")]
        self.assertEqual(agents, ["software-ai-engineering"])

    def test_unregister_removes_module(self):
        registry = ModuleRegistry()
        registry.register(_manifest())
        registry.unregister("agent-factory")
        with self.assertRaises(ModuleNotRegisteredError):
            registry.get("agent-factory")


class _LifecycleProbe:
    def __init__(self, log):
        self._log = log
        self.name = "probe"

    def on_start(self):
        self._log.append(f"{self.name}.start")

    def on_stop(self):
        self._log.append(f"{self.name}.stop")


class TestModuleRegistryLifecycle(unittest.TestCase):
    def test_start_all_calls_on_start_in_registration_order(self):
        registry = ModuleRegistry()
        log: list = []
        for name in ("first", "second"):
            probe = _LifecycleProbe(log)
            probe.name = name
            registry.register(_manifest(name=f"{name}-factory"), instance=probe)

        registry.start_all()

        self.assertEqual(log, ["first.start", "second.start"])

    def test_stop_all_calls_on_stop_in_reverse_order(self):
        registry = ModuleRegistry()
        log: list = []
        for name in ("first", "second"):
            probe = _LifecycleProbe(log)
            probe.name = name
            registry.register(_manifest(name=f"{name}-factory"), instance=probe)

        registry.stop_all()

        self.assertEqual(log, ["second.stop", "first.stop"])

    def test_modules_without_lifecycle_hooks_are_skipped_safely(self):
        registry = ModuleRegistry()
        registry.register(_manifest(), instance="plain-string-has-no-on_start")
        registry.start_all()  # must not raise
        registry.stop_all()  # must not raise

    def test_lifecycle_publishes_events_on_shared_bus(self):
        bus = EventBus()
        received = []
        bus.subscribe("*", lambda e: received.append(e.event_type))
        registry = ModuleRegistry(event_bus=bus)
        registry.register(_manifest())

        registry.start_all()
        registry.stop_all()

        self.assertEqual(
            received,
            [
                "core.module.registered",
                "core.module.started",
                "core.module.stopped",
            ],
        )


if __name__ == "__main__":
    unittest.main()
