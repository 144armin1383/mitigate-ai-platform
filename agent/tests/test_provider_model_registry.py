import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Any, Sequence, Tuple, Optional

from agent.providers.provider_model_registry import (
    ProviderModelRegistry,
    RegistryValidationError,
    RegistryNotFoundError,
    RegistryCorruptionError,
    SecretStore,
    ProjectResolver,
    ProviderAdapter,
)


class DummySecretStore(SecretStore):
    def __init__(self, refs: Dict[str, str] | Dict[str, bool]):
        # values are ignored, only presence matters
        self._refs = {k: True for k in refs.keys()}

    def has_reference(self, reference: str) -> bool:
        return bool(self._refs.get(reference, False))


class DummyProjectResolver:
    def __init__(self, known: Sequence[str]):
        self._known = set(known)

    def is_known_project(self, project_id: str) -> bool:
        return project_id in self._known


class DummyAdapter(ProviderAdapter):
    def __init__(self, models: Sequence[Dict[str, Any]], health_ok: bool = True, error: Optional[str] = None):
        self._models = list(models)
        self._ok = health_ok
        self._error = error

    def list_models(self, provider_config: Dict[str, Any]) -> Sequence[Dict[str, Any]]:
        return list(self._models)

    def test_connectivity(self, provider_config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        return (self._ok, self._error)


class ProviderModelRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.registry_path = self.base / "provider_registry.json"
        self.secret_store = DummySecretStore({"OPENAI_KEY": True, "LOCAL_TOKEN": True})
        self.projects = DummyProjectResolver(["projA", "projB"]) 

    def _make_registry(self, adapters: Dict[str, ProviderAdapter] | None = None) -> ProviderModelRegistry:
        return ProviderModelRegistry(
            self.base,
            secret_store=self.secret_store,
            project_resolver=self.projects,
            provider_adapters=adapters or {},
        )

    def test_provider_creation_and_update_enable_disable(self):
        reg = self._make_registry()
        # Missing credential reference
        with self.assertRaises(RegistryValidationError):
            reg.create_provider({"provider_id": "openai", "display_name": "OpenAI"})
        # Proper creation
        p = reg.create_provider({
            "provider_id": "openai",
            "display_name": "OpenAI",
            "credential_reference": "OPENAI_KEY",
            "enabled": False,
        })
        self.assertEqual(p["status"], "disabled")
        # Enable
        p2 = reg.enable_provider("openai")
        self.assertTrue(p2["enabled"])  # enabled flag
        self.assertEqual(p2["status"], "active")
        # Disable
        p3 = reg.disable_provider("openai")
        self.assertFalse(p3["enabled"]) 
        self.assertEqual(p3["status"], "disabled")
        # Update credential to non-existing ref
        with self.assertRaises(RegistryValidationError):
            reg.update_provider("openai", {"credential_reference": "DOES_NOT_EXIST"})

    def test_secrets_never_serialized(self):
        reg = self._make_registry()
        reg.create_provider({
            "provider_id": "openai",
            "display_name": "OpenAI",
            "credential_reference": "OPENAI_KEY",
        })
        with open(self.registry_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("OPENAI_KEY", content)
        # Ensure no accidental secret values appear (we never stored values anyway)
        self.assertNotIn("sk-", content)
        self.assertNotIn("Authorization", content)

    def test_provider_health_success_and_failure(self):
        # Create provider with adapter
        adapters = {
            "openai": DummyAdapter([], health_ok=True),
        }
        reg = self._make_registry(adapters)
        reg.create_provider({
            "provider_id": "openai",
            "display_name": "OpenAI",
            "credential_reference": "OPENAI_KEY",
            "enabled": True,
        })
        res_ok = reg.test_provider("openai")
        self.assertTrue(res_ok["ok"]) 
        # reconfigure adapter to fail
        reg_fail = self._make_registry({"openai": DummyAdapter([], health_ok=False, error="timeout")})
        # Load persisted provider
        res2 = reg_fail.test_provider("openai")
        self.assertFalse(res2["ok"]) 
        events = reg_fail.latest_events(10)
        self.assertTrue(any(e["type"] == "provider_health_failed" for e in events))
        # Ensure redaction in events
        for e in events:
            self.assertNotIn("credential_reference", e.get("details", {}))

    def test_model_registration_listing_enable_disable_deprecation(self):
        reg = self._make_registry({"openai": DummyAdapter([])})
        reg.create_provider({
            "provider_id": "openai",
            "display_name": "OpenAI",
            "credential_reference": "OPENAI_KEY",
            "enabled": True,
        })
        m1 = reg.register_model({
            "provider_id": "openai",
            "model_id": "gpt-4o",
            "display_name": "GPT-4o",
            "enabled": True,
            "supports_text": True,
            "supports_vision": True,
            "supports_tools": True,
        })
        m2 = reg.register_model({
            "provider_id": "openai",
            "model_id": "gpt-4o-mini",
            "display_name": "GPT-4o Mini",
            "enabled": True,
            "supports_text": True,
            "supports_vision": False,
            "supports_tools": False,
        })
        listed = reg.list_models("openai")
        self.assertEqual([m["model_id"] for m in listed], ["gpt-4o", "gpt-4o-mini"])  # deterministic order
        # Disable model
        reg.disable_model("openai", "gpt-4o-mini")
        self.assertEqual(reg.get_model("openai", "gpt-4o-mini")["status"], "disabled")
        # Refresh with only one model, second should become deprecated
        adapters2 = {
            "openai": DummyAdapter([{
                "model_id": "gpt-4o",
                "display_name": "GPT-4o",
                "supports_text": True,
                "supports_vision": True,
                "supports_tools": True,
                "capabilities": ["chat"],
                "context_window": 100,
                "maximum_output_tokens": 50,
                "supports_json": True,
                "supports_reasoning": False,
                "supports_streaming": True,
            }])
        }
        reg2 = self._make_registry(adapters2)
        # provider already exists; run refresh
        r = reg2.refresh_models("openai")
        self.assertTrue(r.get("refreshed"))
        m2a = reg2.get_model("openai", "gpt-4o-mini")
        self.assertEqual(m2a["status"], "deprecated")

    def test_provider_model_ownership_validation(self):
        reg = self._make_registry()
        reg.create_provider({
            "provider_id": "local",
            "display_name": "Local",
            "credential_reference": "LOCAL_TOKEN",
            "enabled": True,
        })
        reg.register_model({
            "provider_id": "local",
            "model_id": "llama3",
            "display_name": "Llama3",
            "enabled": True,
            "supports_text": True,
            "supports_tools": True,
        })
        with self.assertRaises(RegistryNotFoundError):
            reg.get_model("local", "missing")
        with self.assertRaises(RegistryValidationError):
            reg.register_model({
                "provider_id": "local",
                "model_id": "llama3",  # duplicate
                "display_name": "Llama3",
                "enabled": True,
            })

    def test_task_assignment_and_project_isolation_and_invalid_task_type(self):
        reg = self._make_registry()
        reg.create_provider({"provider_id": "local", "display_name": "Local", "credential_reference": "LOCAL_TOKEN", "enabled": True})
        reg.register_model({"provider_id": "local", "model_id": "llama3", "display_name": "Llama3", "enabled": True, "supports_text": True, "supports_tools": True})
        # Invalid task type
        with self.assertRaises(RegistryValidationError):
            reg.assign_model("projA", "unknown_task", {})
        # Valid assignment
        assign = reg.assign_model("projA", "coding", {
            "primary_provider_id": "local",
            "primary_model_id": "llama3",
            "fallback_chain": [],
        })
        self.assertEqual(assign["project_id"], "projA")
        self.assertEqual(assign["task_type"], "coding")
        # Cross-project isolation
        with self.assertRaises(RegistryNotFoundError):
            reg.get_assignment("projB", "coding")
        lstA = reg.list_assignments("projA")
        lstB = reg.list_assignments("projB")
        self.assertEqual(len(lstA), 1)
        self.assertEqual(len(lstB), 0)

    def test_capability_enforcement_and_selection(self):
        reg = self._make_registry()
        reg.create_provider({"provider_id": "local", "display_name": "Local", "credential_reference": "LOCAL_TOKEN", "enabled": True})
        reg.register_model({"provider_id": "local", "model_id": "txt-only", "display_name": "T", "enabled": True, "supports_text": True, "supports_vision": False, "supports_tools": False})
        reg.register_model({"provider_id": "local", "model_id": "vision", "display_name": "V", "enabled": True, "supports_text": True, "supports_vision": True, "supports_tools": False})
        reg.register_model({"provider_id": "local", "model_id": "tools", "display_name": "Tool", "enabled": True, "supports_text": True, "supports_vision": False, "supports_tools": True})
        # Vision requires vision support
        reg.assign_model("projA", "vision", {"primary_provider_id": "local", "primary_model_id": "txt-only", "fallback_chain": [{"provider_id": "local", "model_id": "vision"}]})
        sel = reg.select_model("projA", "vision")
        self.assertEqual(sel["model_id"], "vision")
        self.assertEqual(sel["source"], "fallback")
        # Coding requires tools
        reg.assign_model("projA", "coding", {"primary_provider_id": "local", "primary_model_id": "txt-only", "fallback_chain": [{"provider_id": "local", "model_id": "tools"}]})
        sel2 = reg.select_model("projA", "coding")
        self.assertEqual(sel2["model_id"], "tools")
        self.assertEqual(sel2["source"], "fallback")

    def test_duplicate_fallback_rejection(self):
        reg = self._make_registry()
        reg.create_provider({"provider_id": "local", "display_name": "Local", "credential_reference": "LOCAL_TOKEN", "enabled": True})
        reg.register_model({"provider_id": "local", "model_id": "m1", "display_name": "M1", "enabled": True, "supports_text": True})
        reg.register_model({"provider_id": "local", "model_id": "m2", "display_name": "M2", "enabled": True, "supports_text": True})
        with self.assertRaises(RegistryValidationError):
            reg.assign_model("projA", "chat", {
                "primary_provider_id": "local",
                "primary_model_id": "m1",
                "fallback_chain": [{"provider_id": "local", "model_id": "m2"}, {"provider_id": "local", "model_id": "m2"}]
            })
        with self.assertRaises(RegistryValidationError):
            reg.assign_model("projA", "chat", {
                "primary_provider_id": "local",
                "primary_model_id": "m1",
                "fallback_chain": [{"provider_id": "local", "model_id": "m1"}]
            })

    def test_unavailable_and_disabled_skipping_and_no_model(self):
        reg = self._make_registry()
        reg.create_provider({"provider_id": "local", "display_name": "Local", "credential_reference": "LOCAL_TOKEN", "enabled": True})
        reg.register_model({"provider_id": "local", "model_id": "ok", "display_name": "OK", "enabled": True, "supports_text": True})
        reg.register_model({"provider_id": "local", "model_id": "off", "display_name": "OFF", "enabled": False, "supports_text": True})
        # select primary ok
        reg.assign_model("projA", "chat", {"primary_provider_id": "local", "primary_model_id": "ok", "fallback_chain": [{"provider_id": "local", "model_id": "off"}]})
        sel = reg.select_model("projA", "chat")
        self.assertEqual(sel["model_id"], "ok")
        # disable provider
        reg.disable_provider("local")
        sel2 = reg.select_model("projA", "chat")
        self.assertEqual(sel2["source"], "none")
        self.assertIsNone(sel2["provider_id"]) 
        # re-enable but mark model unavailable and ensure fallback/none
        reg.enable_provider("local")
        reg.update_model("local", "ok", {"status": "unavailable"})
        sel3 = reg.select_model("projA", "chat")
        self.assertEqual(sel3["source"], "none")

    def test_refresh_failure_preserves_state(self):
        # Initial registry with one model
        reg = self._make_registry({"openai": DummyAdapter([{"model_id": "m1", "display_name": "M1", "supports_text": True}])})
        reg.create_provider({"provider_id": "openai", "display_name": "OpenAI", "credential_reference": "OPENAI_KEY", "enabled": True})
        reg.refresh_models("openai")
        self.assertEqual([m["model_id"] for m in reg.list_models("openai")], ["m1"]) 
        # New registry with failing adapter should preserve previous
        class FailingAdapter(DummyAdapter):
            def list_models(self, provider_config: Dict[str, Any]) -> Sequence[Dict[str, Any]]:
                raise RuntimeError("network down")
        reg2 = self._make_registry({"openai": FailingAdapter([])})
        out = reg2.refresh_models("openai")
        self.assertFalse(out.get("refreshed"))
        self.assertEqual([m["model_id"] for m in reg2.list_models("openai")], ["m1"]) 

    def test_restart_recovery_and_corrupted_storage_rejection(self):
        reg = self._make_registry()
        reg.create_provider({"provider_id": "openrouter", "display_name": "OpenRouter", "credential_reference": "OPENAI_KEY", "enabled": True})
        reg.register_model({"provider_id": "openrouter", "model_id": "any", "display_name": "Any", "enabled": True, "supports_text": True})
        reg.assign_model("projA", "chat", {"primary_provider_id": "openrouter", "primary_model_id": "any", "fallback_chain": []})
        # New instance reading same file should load data
        reg2 = self._make_registry()
        self.assertEqual(len(reg2.list_providers()), 1)
        self.assertEqual(len(reg2.list_models()), 1)
        self.assertEqual(len(reg2.list_assignments("projA")), 1)
        # Corrupt file and expect rejection
        with open(self.registry_path, "w", encoding="utf-8") as f:
            f.write("not-json")
        with self.assertRaises(RegistryCorruptionError):
            self._make_registry()

    def test_deterministic_serialization_and_unrelated_files_unchanged(self):
        reg = self._make_registry()
        other_path = self.base / "other.txt"
        other_path.write_text("hello", encoding="utf-8")
        reg.create_provider({"provider_id": "azure_openai", "display_name": "Azure OpenAI", "credential_reference": "OPENAI_KEY"})
        reg.create_provider({"provider_id": "anthropic", "display_name": "Anthropic", "credential_reference": "OPENAI_KEY"})
        # Ordering by provider_id
        provs = reg.list_providers()
        self.assertEqual([p["provider_id"] for p in provs], ["anthropic", "azure_openai", "openrouter"]) if any(p["provider_id"]=="openrouter" for p in provs) else self.assertEqual([p["provider_id"] for p in provs], ["anthropic", "azure_openai"]) 
        # Ensure unrelated file content unchanged
        self.assertEqual(other_path.read_text(encoding="utf-8"), "hello")

    def test_two_independent_projects_and_custom_provider(self):
        # add custom provider without core changes
        adapters = {"customx": DummyAdapter([])}
        reg = self._make_registry(adapters)
        reg.create_provider({"provider_id": "customx", "display_name": "CustomX", "credential_reference": "OPENAI_KEY", "enabled": True})
        reg.register_model({"provider_id": "customx", "model_id": "mfast", "display_name": "Fast", "enabled": True, "supports_text": True})
        reg.assign_model("projA", "fast_tasks", {"primary_provider_id": "customx", "primary_model_id": "mfast", "fallback_chain": []})
        # independent project
        reg.create_provider({"provider_id": "local", "display_name": "Local", "credential_reference": "LOCAL_TOKEN", "enabled": True})
        reg.register_model({"provider_id": "local", "model_id": "mchat", "display_name": "Chat", "enabled": True, "supports_text": True})
        reg.assign_model("projB", "chat", {"primary_provider_id": "local", "primary_model_id": "mchat", "fallback_chain": []})
        selA = reg.select_model("projA", "fast_tasks")
        selB = reg.select_model("projB", "chat")
        self.assertEqual(selA["provider_id"], "customx")
        self.assertEqual(selB["provider_id"], "local")


if __name__ == "__main__":
    unittest.main()
