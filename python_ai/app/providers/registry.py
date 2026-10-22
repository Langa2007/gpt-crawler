import logging
from typing import Any, Callable, Dict, List, Optional, Type
from python_ai.app.config import settings
from python_ai.app.providers.base import BaseAIProvider
from python_ai.app.providers.gemini_provider import GeminiProvider
from python_ai.app.providers.openai_provider import OpenAIProvider
from python_ai.app.providers.claude_provider import ClaudeProvider
from python_ai.app.providers.kimi_provider import KimiProvider
from python_ai.app.providers.qwen_provider import QwenProvider
from python_ai.app.providers.custom_provider import CustomProvider

logger = logging.getLogger(__name__)

# Default priority order for auto-detecting configured providers
AUTO_DETECT_PRIORITY = ["gemini", "openai", "claude", "kimi", "qwen", "custom"]


class ProviderRegistry:
    def __init__(self):
        self._provider_classes: Dict[str, Type[BaseAIProvider]] = {}
        self._instances: Dict[str, BaseAIProvider] = {}
        self._register_builtins()

    def _register_builtins(self):
        self.register("gemini", GeminiProvider)
        self.register("google", GeminiProvider)
        self.register("openai", OpenAIProvider)
        self.register("chatgpt", OpenAIProvider)
        self.register("claude", ClaudeProvider)
        self.register("anthropic", ClaudeProvider)
        self.register("kimi", KimiProvider)
        self.register("moonshot", KimiProvider)
        self.register("qwen", QwenProvider)
        self.register("dashscope", QwenProvider)
        self.register("custom", CustomProvider)
        self.register("ollama", CustomProvider)
        self.register("deepseek", CustomProvider)
        self.register("local", CustomProvider)

    def register(self, name: str, provider_cls: Type[BaseAIProvider]):
        """Register a new AI provider class with a given name."""
        clean_name = name.strip().lower()
        self._provider_classes[clean_name] = provider_cls
        # Evict old cached instance if exists
        self._instances.pop(clean_name, None)

    def get_provider(self, name: Optional[str] = None) -> Optional[BaseAIProvider]:
        """
        Get an instantiated AI provider.
        1. If 'name' is specified, return that provider if configured.
        2. Else if settings.ai_provider is specified, return it.
        3. Else auto-detect the first configured provider from AUTO_DETECT_PRIORITY.
        4. If no provider is configured, return None.
        """
        target_name = (name or settings.ai_provider or "").strip().lower()

        if target_name:
            provider = self._get_or_create(target_name)
            if provider and provider.is_configured():
                return provider
            if provider and not provider.is_configured():
                logger.warning("Requested AI provider '%s' is not configured with valid credentials.", target_name)

        # Auto-detect among priority list
        for candidate in AUTO_DETECT_PRIORITY:
            p = self._get_or_create(candidate)
            if p and p.is_configured():
                return p

        return None

    def _get_or_create(self, name: str) -> Optional[BaseAIProvider]:
        clean_name = name.strip().lower()
        if clean_name in self._instances:
            return self._instances[clean_name]

        cls = self._provider_classes.get(clean_name)
        if cls is None:
            return None

        try:
            instance = cls()
            self._instances[clean_name] = instance
            return instance
        except Exception as e:
            logger.error("Failed to instantiate provider '%s': %s", clean_name, e)
            return None

    def get_active_provider_name(self) -> str:
        active = self.get_provider()
        return active.name if active else "heuristic"

    def list_providers(self) -> Dict[str, Dict[str, Any]]:
        """List canonical providers and their configuration status."""
        canonical = ["gemini", "openai", "claude", "kimi", "qwen", "custom"]
        result = {}
        for name in canonical:
            p = self._get_or_create(name)
            if p:
                result[name] = {
                    "configured": p.is_configured(),
                    "default_model": p.get_default_model(),
                }
            else:
                result[name] = {"configured": False, "default_model": ""}
        return result


# Global singleton registry
registry = ProviderRegistry()


def register_provider(name: str) -> Callable[[Type[BaseAIProvider]], Type[BaseAIProvider]]:
    """Decorator to easily register custom AI providers."""
    def decorator(cls: Type[BaseAIProvider]) -> Type[BaseAIProvider]:
        registry.register(name, cls)
        return cls
    return decorator

