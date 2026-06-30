from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IoTUiPlacementTests(unittest.TestCase):
    def test_iot_actions_are_managed_from_iot_pipelines_page(self):
        settings_page = (ROOT / "src/settingsPage.jsx").read_text(encoding="utf-8")
        iot_page = (ROOT / "src/iotPipelinesPage.jsx").read_text(encoding="utf-8")

        self.assertNotIn("<h3>IoT actions</h3>", settings_page)
        self.assertIn("<h3>IoT actions</h3>", iot_page)
        self.assertIn("+ Add action", iot_page)
        self.assertIn("IoT control agents", iot_page)

    def test_settings_page_points_iot_work_to_iot_pipelines(self):
        settings_page = (ROOT / "src/settingsPage.jsx").read_text(encoding="utf-8")

        self.assertIn("IoT devices live in IoT Pipelines", settings_page)
        self.assertIn("Agent LLM providers", settings_page)


if __name__ == "__main__":
    unittest.main()
