from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.runner import run_flow


def mock_workflow_settings(mode: str = "direct") -> dict:
    return {"agentExecution": {"fileWriteMode": mode, "maxFileBlocks": 20, "allowMockProvider": True}}


class RunnerFileWriteTests(unittest.IsolatedAsyncioTestCase):
    async def test_developer_agent_writes_file_blocks_directly_by_default(self):
        with tempfile.TemporaryDirectory() as workspace:
            logs = await run_flow(
                flow=[{"id": "step-1", "agentId": "developer-agent", "dependsOnPrevious": True}],
                agents=[
                    {
                        "id": "developer-agent",
                        "name": "Developer Agent",
                        "role": "Developer",
                        "provider": "mock",
                        "model": "mock-model",
                        "temperature": 0.2,
                        "skills": ["developer", "file_write"],
                        "mcps": [],
                        "systemPrompt": "You write files.",
                    }
                ],
                skills=[{"id": "developer", "name": "Developer", "description": "Writes code"}],
                mcps=[],
                task="Add python backend API feature",
                workspace_root=workspace,
                runtime_settings=mock_workflow_settings("direct"),
            )

            self.assertTrue((Path(workspace) / "app/generated_feature.py").exists())
            self.assertTrue((Path(workspace) / "tests/test_generated_feature.py").exists())
            self.assertIn("app/generated_feature.py", logs[0]["generatedFiles"])

    async def test_review_mode_stages_file_blocks_for_human_review(self):
        with tempfile.TemporaryDirectory() as workspace:
            logs = await run_flow(
                flow=[{"id": "step-1", "agentId": "developer-agent", "dependsOnPrevious": True}],
                agents=[
                    {
                        "id": "developer-agent",
                        "name": "Developer Agent",
                        "role": "Developer",
                        "provider": "mock",
                        "model": "mock-model",
                        "temperature": 0.2,
                        "skills": ["developer", "file_write"],
                        "mcps": [],
                    }
                ],
                skills=[{"id": "developer", "name": "Developer", "description": "Writes code"}],
                mcps=[],
                task="Add python backend API feature",
                workspace_root=workspace,
                runtime_settings=mock_workflow_settings("review"),
            )

            self.assertFalse((Path(workspace) / "app/generated_feature.py").exists())
            self.assertTrue((Path(workspace) / "agent-flow-output/generated/developer-agent/app/generated_feature.py").exists())
            self.assertIn("agent-flow-output/generated/developer-agent/app/generated_feature.py", logs[0]["generatedFiles"])


    async def test_non_writer_agent_cannot_write_source_file_blocks(self):
        from app import runner

        original_call_llm = runner.call_llm

        async def fake_call_llm(**kwargs):
            return """```file path="src/app.py"
print("should not write")
```
```file path="README.md"
# notes
```"""

        runner.call_llm = fake_call_llm
        try:
            with tempfile.TemporaryDirectory() as workspace:
                events = []
                logs = await run_flow(
                    flow=[{"id": "step-1", "agentId": "requirements-agent", "dependsOnPrevious": True}],
                    agents=[{"id": "requirements-agent", "name": "Requirements", "role": "Requirements", "provider": "mock", "skills": ["research", "summary"], "mcps": []}],
                    skills=[],
                    mcps=[],
                    task="Plan a project",
                    workspace_root=workspace,
                    runtime_settings={"agentExecution": {"fileWriteMode": "direct", "maxFileBlocks": 20}},
                    on_event=lambda event: events.append(event),
                )

                self.assertFalse((Path(workspace) / "src/app.py").exists())
                self.assertFalse((Path(workspace) / "README.md").exists())
                self.assertEqual(logs[0]["generatedFiles"], [])
                self.assertTrue(any(event.get("type") == "warning" and "Skipped file block" in event.get("message", "") for event in events))
        finally:
            runner.call_llm = original_call_llm

    async def test_qa_agent_can_write_tests_but_not_source(self):
        from app import runner

        original_call_llm = runner.call_llm

        async def fake_call_llm(**kwargs):
            return """```file path="src/app.py"
print("source")
```
```file path="tests/test_app.py"
def test_ok():
    assert True
```"""

        runner.call_llm = fake_call_llm
        try:
            with tempfile.TemporaryDirectory() as workspace:
                logs = await run_flow(
                    flow=[{"id": "step-1", "agentId": "qa-agent", "dependsOnPrevious": True}],
                    agents=[{"id": "qa-agent", "name": "QA", "role": "QA", "provider": "mock", "skills": ["qa", "tester"], "mcps": []}],
                    skills=[],
                    mcps=[],
                    task="Review tests",
                    workspace_root=workspace,
                    runtime_settings={"agentExecution": {"fileWriteMode": "direct", "maxFileBlocks": 20}},
                )

                self.assertFalse((Path(workspace) / "src/app.py").exists())
                self.assertTrue((Path(workspace) / "tests/test_app.py").exists())
                self.assertEqual(logs[0]["generatedFiles"], ["tests/test_app.py"])
        finally:
            runner.call_llm = original_call_llm

    async def test_missing_agent_is_logged(self):
        with tempfile.TemporaryDirectory() as workspace:
            events = []
            logs = await run_flow(
                flow=[{"id": "step-1", "agentId": "missing-agent", "dependsOnPrevious": True}],
                agents=[],
                skills=[],
                mcps=[],
                task="Run missing step",
                workspace_root=workspace,
                runtime_settings={"agentExecution": {"fileWriteMode": "direct", "maxFileBlocks": 20}},
                on_event=lambda event: events.append(event),
            )

            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["error"], "agent_not_found")
            self.assertTrue(any(event.get("type") == "warning" and "agent not found" in event.get("message", "") for event in events))

    async def test_unconfigured_workflow_provider_is_logged_without_mock_fallback(self):
        with tempfile.TemporaryDirectory() as workspace:
            events = []
            logs = await run_flow(
                flow=[{"id": "step-1", "agentId": "developer-agent", "dependsOnPrevious": True}],
                agents=[
                    {
                        "id": "developer-agent",
                        "name": "Developer Agent",
                        "role": "Developer",
                        "provider": "gemini",
                        "model": "gemini-test",
                        "temperature": 0.2,
                        "skills": ["developer", "file_write"],
                        "mcps": [],
                    }
                ],
                skills=[],
                mcps=[],
                task="Add python backend API feature",
                workspace_root=workspace,
                runtime_settings={"agentExecution": {"fileWriteMode": "direct", "maxFileBlocks": 20}},
                on_event=lambda event: events.append(event),
            )

            self.assertEqual(logs[0]["error"], "provider_not_configured")
            self.assertIn("env keys are not used by workflow agents", logs[0]["output"])
            self.assertEqual(logs[0]["generatedFiles"], [])
            self.assertFalse((Path(workspace) / "app/generated_feature.py").exists())
            self.assertTrue(any(event.get("type") == "error" and "workflow agents" in event.get("message", "") for event in events))

    async def test_iot_tool_step_executes_action_without_llm_provider(self):
        from app import runner

        original_execute = runner.execute_iot_action
        calls = []

        async def fake_execute(action_id, command, settings, approved=False, dry_run=None):
            calls.append({"action_id": action_id, "command": command, "approved": approved, "dry_run": dry_run})
            return {"ok": True, "dryRun": dry_run, "actionId": action_id, "command": command}

        runner.execute_iot_action = fake_execute
        try:
            logs = await run_flow(
                flow=[
                    {
                        "id": "step-1",
                        "agentId": "iot-device-manager",
                        "iotActionIds": ["tuya-plug"],
                        "iotCommand": "turn_on",
                        "iotApproved": True,
                        "iotDryRun": False,
                        "iotToolOnly": True,
                    }
                ],
                agents=[{"id": "iot-device-manager", "name": "IoT Device Manager", "role": "Control", "skills": ["device_control"], "mcps": []}],
                skills=[],
                mcps=[],
                task="Turn on outlet",
                runtime_settings={},
            )

            self.assertEqual(calls, [{"action_id": "tuya-plug", "command": "turn_on", "approved": True, "dry_run": False}])
            self.assertTrue(logs[0]["iotResults"][0]["ok"])
            self.assertNotIn("provider_not_configured", logs[0].get("error") or "")
        finally:
            runner.execute_iot_action = original_execute


if __name__ == "__main__":
    unittest.main()
