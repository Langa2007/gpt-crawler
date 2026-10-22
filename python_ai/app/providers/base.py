import abc
from typing import Any, Dict, List, Optional


class BaseAIProvider(abc.ABC):
    """
    Abstract base class for all AI synthesis & chat providers.
    Implement this class to add custom LLMs to the Scrapper bot.
    """

    name: str = "base"

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """Returns True if the provider has all required credentials/config."""
        pass

    @abc.abstractmethod
    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        """
        Single-turn generation for answer synthesis.
        Must return the generated text response string.
        """
        pass

    @abc.abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        """
        Multi-turn chat completion.
        messages format: [{"role": "user"|"assistant", "content": "..."}]
        Must return the assistant's reply text.
        """
        pass

    def get_default_model(self) -> str:
        """Returns the default model identifier for this provider."""
        return ""

