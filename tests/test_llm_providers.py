from __future__ import annotations

import unittest

from app import llm
from app.llm import ProviderConfigurationError, available_providers, mock_llm


class LlmProviderTests(unittest.TestCase):
    def test_available_providers_include_local_and_cloud_options(self):
        provider_ids = {provider["id"] for provider in available_providers()}
        self.assertTrue({"mock", "openai", "ollama", "gemini", "anthropic"}.issubset(provider_ids))

    def test_mock_developer_outputs_real_file_blocks(self):
        prompt = (
            "AGENT ROLE:\nDeveloper\n\nAGENT SKILLS:\n- Developer: Writes code\n\n"
            "USER TASK:\nAdd python backend API feature\n\nSTEP COMMENT / EXTRA PROMPT:\n-\n\n"
            "PREVIOUS OUTPUT:\n-\n\nIMPORTANT EXECUTION RULES:\n- Return concrete output."
        )
        output = mock_llm(model="mock-model", temperature=0.2, prompt=prompt)
        self.assertIn('```file path="app/generated_feature.py"', output)
        self.assertIn('```file path="tests/test_generated_feature.py"', output)

    def test_openai_response_text_extraction_handles_nested_output(self):
        data = {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": '```file path="README.md"\n# ok\n```',
                        }
                    ]
                }
            ]
        }

        self.assertIn('file path="README.md"', llm._extract_openai_text(data))


class LlmProviderAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_gemini_key = llm.config.GEMINI_API_KEY
        self.original_anthropic_key = llm.config.ANTHROPIC_API_KEY
        self.original_call_openai = llm._call_openai
        self.original_call_gemini = llm._call_gemini
        self.original_call_anthropic = llm._call_anthropic

    async def asyncTearDown(self):
        llm.config.GEMINI_API_KEY = self.original_gemini_key
        llm.config.ANTHROPIC_API_KEY = self.original_anthropic_key
        llm._call_openai = self.original_call_openai
        llm._call_gemini = self.original_call_gemini
        llm._call_anthropic = self.original_call_anthropic

    async def test_assistant_cloud_providers_without_keys_fall_back_to_mock(self):
        llm.config.GEMINI_API_KEY = ""
        llm.config.ANTHROPIC_API_KEY = ""

        gemini_output = await llm.call_llm(provider="gemini", model="gemini-test", temperature=0.1, prompt="hello")
        claude_output = await llm.call_llm(provider="claude", model="claude-test", temperature=0.1, prompt="hello")

        self.assertIn("MOCK OUTPUT - gemini-test", gemini_output)
        self.assertIn("MOCK OUTPUT - claude-test", claude_output)

    async def test_workflow_provider_without_runtime_key_does_not_fall_back_to_mock(self):
        llm.config.GEMINI_API_KEY = "env-key-for-assistant-only"

        with self.assertRaises(ProviderConfigurationError) as ctx:
            await llm.call_llm(provider="gemini", model="gemini-test", temperature=0.1, prompt="hello", runtime_settings={}, usage="workflow")

        self.assertIn("env keys are not used by workflow agents", str(ctx.exception))

    async def test_provider_dispatch_uses_configured_provider(self):
        llm.config.GEMINI_API_KEY = "test-key"
        captured = {}

        async def fake_gemini(model, temperature, prompt, api_key=None):
            captured.update({"model": model, "temperature": temperature, "prompt": prompt})
            return "gemini ok"

        llm._call_gemini = fake_gemini

        output = await llm.call_llm(provider="gemini", model="gemini-1.5-flash", temperature="0.4", prompt="Build a workflow")

        self.assertEqual(output, "gemini ok")
        self.assertEqual(captured, {"model": "gemini-1.5-flash", "temperature": "0.4", "prompt": "Build a workflow"})

    async def test_claude_alias_dispatches_to_anthropic_client(self):
        llm.config.ANTHROPIC_API_KEY = "test-key"
        captured = {}

        async def fake_anthropic(model, temperature, prompt, api_key=None):
            captured.update({"model": model, "temperature": temperature, "prompt": prompt})
            return "claude ok"

        llm._call_anthropic = fake_anthropic

        output = await llm.call_llm(provider="claude", model="claude-3-5-sonnet-latest", temperature=0.2, prompt="Review code")

        self.assertEqual(output, "claude ok")
        self.assertEqual(captured["model"], "claude-3-5-sonnet-latest")

    async def test_runtime_settings_key_configures_cloud_provider(self):
        llm.config.GEMINI_API_KEY = ""
        captured = {}

        async def fake_gemini(model, temperature, prompt, api_key=None):
            captured.update({"model": model, "api_key": api_key})
            return "runtime gemini ok"

        llm._call_gemini = fake_gemini
        runtime_settings = {
            "llmProviders": [
                {"id": "gemini", "name": "Gemini", "enabled": True, "defaultModel": "gemini-runtime", "apiKey": "runtime-key"}
            ]
        }

        output = await llm.call_llm(provider="gemini", temperature=0.2, prompt="hello", runtime_settings=runtime_settings, usage="workflow")

        self.assertEqual(output, "runtime gemini ok")
        self.assertEqual(captured, {"model": "gemini-runtime", "api_key": "runtime-key"})

    async def test_custom_openai_compatible_provider_uses_runtime_base_url(self):
        captured = {}

        async def fake_openai(model, temperature, prompt, api_key=None, base_url=None):
            captured.update({"model": model, "api_key": api_key, "base_url": base_url})
            return "custom ok"

        llm._call_openai = fake_openai
        runtime_settings = {
            "llmProviders": [
                {
                    "id": "local-openai",
                    "name": "Local OpenAI-compatible",
                    "providerKind": "openai",
                    "defaultModel": "local-model",
                    "apiKey": "local-key",
                    "baseUrl": "http://localhost:9999/v1",
                }
            ]
        }

        output = await llm.call_llm(provider="local-openai", temperature=0.2, prompt="hello", runtime_settings=runtime_settings, usage="workflow")

        self.assertEqual(output, "custom ok")
        self.assertEqual(captured, {"model": "local-model", "api_key": "local-key", "base_url": "http://localhost:9999/v1"})


if __name__ == "__main__":
    unittest.main()
