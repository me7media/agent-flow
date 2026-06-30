from __future__ import annotations

import unittest

from app.iot import IoTContextBuilder, default_iot_agents, default_iot_flows, normalize_signal, simulate_action
from app.settings_service import SECRET_MASK, agent_execution_config, default_runtime_settings, public_runtime_settings, upsert_runtime_settings


class RuntimeSettingsTests(unittest.TestCase):
    def test_public_settings_masks_provider_keys(self):
        settings = default_runtime_settings()
        settings["llmProviders"][1]["apiKey"] = "secret"

        public = public_runtime_settings(settings)

        self.assertEqual(public["llmProviders"][1]["apiKey"], SECRET_MASK)

    def test_upsert_keeps_existing_secret_when_mask_is_submitted(self):
        db = {"settings": []}
        saved = upsert_runtime_settings(db, {"llmProviders": [{"id": "gemini", "apiKey": "secret"}]})
        updated = upsert_runtime_settings(db, {"llmProviders": [{"id": "gemini", "apiKey": SECRET_MASK, "defaultModel": "gemini-new"}]})

        gemini = next(provider for provider in updated["llmProviders"] if provider["id"] == "gemini")
        self.assertEqual(gemini["apiKey"], "secret")
        self.assertEqual(gemini["defaultModel"], "gemini-new")
        self.assertEqual(saved["id"], "runtime-settings")

    def test_agent_execution_defaults_to_review_file_writes(self):
        settings = default_runtime_settings()

        execution = agent_execution_config(settings)

        self.assertEqual(execution["fileWriteMode"], "review")
        self.assertEqual(execution["maxFileBlocks"], 20)
        self.assertFalse(execution["allowMockProvider"])


class IoTDomainTests(unittest.TestCase):
    def test_iot_defaults_include_gesture_gate_pipeline(self):
        agents = {agent["id"] for agent in default_iot_agents()}
        flows = {flow["id"]: flow for flow in default_iot_flows()}

        self.assertIn("iot-device-manager", agents)
        self.assertIn("iot-camera-gesture-gate", flows)
        self.assertEqual(flows["iot-camera-gesture-gate"]["category"], "iot")

    def test_context_builder_exposes_selected_sources_and_actions(self):
        settings = default_runtime_settings()
        step = {"iotSourceIds": ["front-yard-camera"], "iotActionIds": ["driveway-gate"]}
        context = IoTContextBuilder(settings).context_for_step(step, {})

        self.assertIn("Front yard camera", context)
        self.assertIn("Driveway gate controller", context)
        self.assertIn("Safety rule", context)

    def test_signal_and_action_simulation_are_normalized(self):
        settings = default_runtime_settings()
        signal = normalize_signal({"sourceId": "front-yard-camera", "summary": "hand up"}, settings)
        action = simulate_action("driveway-gate", "open", settings)

        self.assertEqual(signal.kind, "camera")
        self.assertTrue(action["dryRun"])
        self.assertTrue(action["requiresApproval"])


if __name__ == "__main__":
    unittest.main()
