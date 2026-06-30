from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.runner import run_flow


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
                runtime_settings={"agentExecution": {"fileWriteMode": "direct", "maxFileBlocks": 20}},
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
                runtime_settings={"agentExecution": {"fileWriteMode": "review", "maxFileBlocks": 20}},
            )

            self.assertFalse((Path(workspace) / "app/generated_feature.py").exists())
            self.assertTrue((Path(workspace) / "agent-flow-output/generated/developer-agent/app/generated_feature.py").exists())
            self.assertIn("agent-flow-output/generated/developer-agent/app/generated_feature.py", logs[0]["generatedFiles"])


if __name__ == "__main__":
    unittest.main()
