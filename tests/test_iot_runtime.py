from __future__ import annotations

import unittest
from fastapi.testclient import TestClient

from app import main
from app.iot_runtime import adapter_catalog, discover_iot_devices, execute_iot_action, read_iot_source
from app.settings_service import default_runtime_settings


class IoTRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_iot_actions = main.config.IOT_DEVICE_ACTIONS_ENABLED
        self.original_iot_hosts = list(main.config.IOT_ALLOWED_HOSTS)

    async def asyncTearDown(self):
        main.config.IOT_DEVICE_ACTIONS_ENABLED = self.original_iot_actions
        main.config.IOT_ALLOWED_HOSTS = self.original_iot_hosts

    async def test_adapter_catalog_explains_real_capabilities(self):
        catalog = adapter_catalog()

        self.assertTrue(any(item["id"] == "wifi-http" and item["can_execute"] for item in catalog))
        self.assertTrue(any(item["id"] == "bluetooth-inventory" for item in catalog))

    async def test_http_source_read_is_blocked_without_allowlist(self):
        settings = default_runtime_settings()
        settings["iotSources"].append({"id": "http-source", "name": "HTTP source", "kind": "sensor", "transport": "wifi/http", "endpoint": "http://192.168.1.10/status", "dataType": "json", "enabled": True})

        result = await read_iot_source("http-source", settings)

        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])

    async def test_rtsp_source_reports_gateway_guidance(self):
        settings = default_runtime_settings()

        result = await read_iot_source("front-yard-camera", settings)

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "configured")

    async def test_action_execute_defaults_to_dry_run_when_real_actions_disabled(self):
        main.config.IOT_DEVICE_ACTIONS_ENABLED = False
        settings = default_runtime_settings()

        result = await execute_iot_action("driveway-gate", "open", settings, approved=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["dryRun"])

    async def test_tasmota_action_builds_get_request_plan(self):
        main.config.IOT_DEVICE_ACTIONS_ENABLED = False
        settings = default_runtime_settings()
        settings["iotActions"].append(
            {
                "id": "office-plug",
                "name": "Office plug",
                "kind": "smart_plug",
                "transport": "wifi/http",
                "endpoint": "http://192.168.0.55",
                "adapter": "tasmota",
                "commands": ["turn_on", "turn_off"],
                "requiresApproval": True,
                "enabled": True,
            }
        )

        result = await execute_iot_action("office-plug", "turn_on", settings, approved=True)

        self.assertTrue(result["dryRun"])
        self.assertEqual(result["request"]["method"], "GET")
        self.assertEqual(result["request"]["url"], "http://192.168.0.55/cm?cmnd=Power+On")

    async def test_custom_command_map_builds_request_plan(self):
        main.config.IOT_DEVICE_ACTIONS_ENABLED = False
        settings = default_runtime_settings()
        settings["iotActions"].append(
            {
                "id": "lab-plug",
                "name": "Lab plug",
                "kind": "smart_plug",
                "transport": "wifi/http",
                "endpoint": "http://192.168.0.60/api/device",
                "commands": ["turn_on", "turn_off"],
                "commandMap": {
                    "turn_on": {"method": "PUT", "path": "/api/device/state", "json": {"state": "on", "device": "{{actionId}}"}},
                    "turn_off": {"method": "PUT", "path": "/api/device/state", "json": {"state": "off", "device": "{{actionId}}"}},
                },
                "requiresApproval": True,
                "enabled": True,
            }
        )

        result = await execute_iot_action("lab-plug", "turn_off", settings, approved=True)

        self.assertEqual(result["request"]["method"], "PUT")
        self.assertEqual(result["request"]["url"], "http://192.168.0.60/api/device/state")
        self.assertEqual(result["request"]["json"], {"state": "off", "device": "lab-plug"})

    async def test_tuya_local_requires_local_key(self):
        main.config.IOT_DEVICE_ACTIONS_ENABLED = True
        main.config.IOT_ALLOWED_HOSTS = ["192.168.0.100"]
        settings = default_runtime_settings()
        settings["iotActions"].append(
            {
                "id": "tuya-plug",
                "name": "Tuya plug",
                "kind": "smart_plug",
                "transport": "tuya-local",
                "endpoint": "192.168.0.100",
                "adapter": "tuya-local",
                "deviceId": "bf60bd5c14400e69b1nplq",
                "version": "3.3",
                "commands": ["turn_on", "turn_off"],
                "requiresApproval": True,
                "enabled": True,
            }
        )

        result = await execute_iot_action("tuya-plug", "turn_on", settings, approved=True, dry_run=False)

        self.assertFalse(result["ok"])
        self.assertIn("localKey", result["message"])

    async def test_tuya_discovery_maps_scan_to_suggested_action(self):
        from app import iot_runtime

        original_import = iot_runtime.__import__ if hasattr(iot_runtime, "__import__") else None
        original_to_thread = iot_runtime.asyncio.to_thread

        async def fake_to_thread(func, *args, **kwargs):
            return {
                "192.168.0.100": {
                    "ip": "192.168.0.100",
                    "gwId": "bf60bd5c14400e69b1nplq",
                    "encrypt": True,
                    "productKey": "product",
                    "version": "3.3",
                    "name": "Outlet",
                }
            }

        iot_runtime.asyncio.to_thread = fake_to_thread
        try:
            result = await discover_iot_devices({"transport": "tuya-local"})
        finally:
            iot_runtime.asyncio.to_thread = original_to_thread

        self.assertTrue(result["ok"])
        self.assertEqual(result["devices"][0]["suggestedAction"]["adapter"], "tuya-local")
        self.assertEqual(result["devices"][0]["suggestedAction"]["deviceId"], "bf60bd5c14400e69b1nplq")

    async def test_non_http_discovery_returns_gateway_guidance(self):
        result = await discover_iot_devices({"transport": "mqtt"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["devices"], [])
        self.assertIn("gateway", result["notes"].lower())


class IoTRuntimeEndpointTests(unittest.TestCase):
    def test_iot_runtime_endpoints_are_available(self):
        client = TestClient(main.app)

        adapters = client.get("/api/iot/adapters")
        dry_run = client.post("/api/iot/actions/execute", json={"actionId": "driveway-gate", "command": "open", "approved": True})

        self.assertEqual(adapters.status_code, 200)
        self.assertTrue(adapters.json()["adapters"])
        self.assertEqual(dry_run.status_code, 200)
        self.assertTrue(dry_run.json()["dryRun"])


if __name__ == "__main__":
    unittest.main()
