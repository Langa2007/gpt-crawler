from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import pytest

from python_ai.app.config import settings
from python_ai.app.providers.base import BaseAIProvider
from python_ai.app.providers.registry import ProviderRegistry, register_provider
from python_ai.app.providers.openai_provider import OpenAIProvider
from python_ai.app.providers.claude_provider import ClaudeProvider
from python_ai.app.providers.kimi_provider import KimiProvider
from python_ai.app.providers.qwen_provider import QwenProvider
from python_ai.app.providers.custom_provider import CustomProvider
from python_ai.app.providers.gemini_provider import GeminiProvider
from python_ai.app.ai_synthesizer import AISynthesizer


def test_custom_provider_registration():
    reg = ProviderRegistry()

    class MockKimi(BaseAIProvider):
        name = "mock_kimi"

        def is_configured(self) -> bool:
            return True

        def generate(self, prompt: str, system: Optional[str] = None, model: Optional[str] = None, max_tokens: int = 2048) -> str:
            return f"Answer from mock kimi: {prompt[:10]}"

        def chat(self, messages: List[Dict[str, str]], system: Optional[str] = None, model: Optional[str] = None, max_tokens: int = 2048) -> str:
            return "Chat reply from mock kimi"

    reg.register("mock_kimi", MockKimi)
    provider = reg.get_provider("mock_kimi")
    assert provider is not None
    assert provider.name == "mock_kimi"
    assert provider.generate("hello world") == "Answer from mock kimi: hello worl"
    assert provider.chat([{"role": "user", "content": "hi"}]) == "Chat reply from mock kimi"


def test_registry_auto_detect_empty():
    reg = ProviderRegistry()
    # When no keys are configured, get_provider() returns None
    with patch.object(settings, "gemini_api_key", ""), \
         patch.object(settings, "openai_api_key", ""), \
         patch.object(settings, "anthropic_api_key", ""), \
         patch.object(settings, "kimi_api_key", ""), \
         patch.object(settings, "qwen_api_key", ""), \
         patch.object(settings, "custom_ai_base_url", ""), \
         patch.object(settings, "ai_provider", ""):
        provider = reg.get_provider()
        assert provider is None
        assert reg.get_active_provider_name() == "heuristic"


def test_registry_priority_selection():
    reg = ProviderRegistry()
    with patch.object(settings, "gemini_api_key", ""), \
         patch.object(settings, "openai_api_key", "sk-fake-openai"), \
         patch.object(settings, "anthropic_api_key", "sk-ant-fake"), \
         patch.object(settings, "ai_provider", ""):
        # OpenAI should be chosen before Claude in auto-detect priority
        provider = reg.get_provider()
        assert provider is not None
        assert provider.name == "openai"

    # But if explicitly requested Claude:
    with patch.object(settings, "openai_api_key", "sk-fake-openai"), \
         patch.object(settings, "anthropic_api_key", "sk-ant-fake"), \
         patch.object(settings, "ai_provider", "claude"):
        provider = reg.get_provider()
        assert provider is not None
        assert provider.name == "claude"


def test_openai_provider_mocked_http():
    provider = OpenAIProvider()
    with patch.object(settings, "openai_api_key", "sk-test-key"):
        assert provider.is_configured() is True

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "OpenAI generated synthesis"}}]
        }

        with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
            result = provider.generate("What is quantum computing?")
            assert result == "OpenAI generated synthesis"
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert "Authorization" in call_kwargs["headers"]
            assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test-key"


def test_claude_provider_mocked_http():
    provider = ClaudeProvider()
    with patch.object(settings, "anthropic_api_key", "sk-ant-test-key"):
        assert provider.is_configured() is True

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "Claude synthesized answer"}]
        }

        with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
            result = provider.generate("Analyze solar energy trends", system="You are an analyst.")
            assert result == "Claude synthesized answer"
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["headers"]["x-api-key"] == "sk-ant-test-key"
            assert call_kwargs["json"]["system"] == "You are an analyst."


def test_kimi_provider_mocked_http():
    provider = KimiProvider()
    with patch.object(settings, "kimi_api_key", "sk-kimi-key"):
        assert provider.is_configured() is True

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Kimi answer"}}]
        }

        with patch("httpx.Client.post", return_value=mock_resp):
            result = provider.generate("Query")
            assert result == "Kimi answer"


def test_qwen_provider_mocked_http():
    provider = QwenProvider()
    with patch.object(settings, "qwen_api_key", "sk-qwen-key"):
        assert provider.is_configured() is True

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Qwen answer"}}]
        }

        with patch("httpx.Client.post", return_value=mock_resp):
            result = provider.generate("Query")
            assert result == "Qwen answer"


def test_custom_provider_mocked_http():
    provider = CustomProvider()
    with patch.object(settings, "custom_ai_base_url", "http://localhost:11434/v1"):
        assert provider.is_configured() is True

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Local Ollama/DeepSeek answer"}}]
        }

        with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
            result = provider.generate("Query")
            assert result == "Local Ollama/DeepSeek answer"
            assert "chat/completions" in mock_post.call_args[0][0]


def test_ai_synthesizer_with_provider():
    synth = AISynthesizer()

    class MockProvider(BaseAIProvider):
        name = "test_ai"

        def is_configured(self) -> bool:
            return True

        def generate(self, prompt: str, system: Optional[str] = None, model: Optional[str] = None, max_tokens: int = 2048) -> str:
            return "Synthesized result [1]"

        def chat(self, messages: List[Dict[str, str]], system: Optional[str] = None, model: Optional[str] = None, max_tokens: int = 2048) -> str:
            return "Chat reply"

    synth.registry.register("test_ai", MockProvider)

    docs = [{"title": "Doc 1", "url": "https://example.com", "text": "Content about science"}]
    res = synth.synthesize_answer("What is science?", docs, provider="test_ai")
    assert res["confidence"] == "high"
    assert res["provider_used"] == "test_ai"
    assert res["answer"] == "Synthesized result [1]"
    assert len(res["sources"]) == 1
    assert res["sources"][0]["id"] == 1

