import logging
from typing import Any, Dict, List, Optional
from python_ai.app.config import settings
from python_ai.app.providers.base import BaseAIProvider

logger = logging.getLogger(__name__)


class GeminiProvider(BaseAIProvider):
    name = "gemini"

    def __init__(self):
        self._client = None
        self._init_client()

    def _init_client(self):
        if self.is_configured():
            try:
                from google import genai
                self._client = genai.Client(api_key=settings.gemini_api_key)
            except Exception as e:
                logger.warning("Could not initialize Google GenAI client: %s", e)
                self._client = None

    def is_configured(self) -> bool:
        return bool(settings.gemini_api_key and settings.gemini_api_key.strip())

    def get_default_model(self) -> str:
        return settings.gemini_model or "gemini-2.5-flash"

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        if self._client is None:
            self._init_client()
        if self._client is None:
            raise RuntimeError("Gemini client is not configured or failed to initialize.")

        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        target_model = model or self.get_default_model()
        response = self._client.models.generate_content(  # pyright: ignore[reportUnknownMemberType]
            model=target_model,
            contents=full_prompt,
        )
        return response.text or ""

    def chat(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        if self._client is None:
            self._init_client()
        if self._client is None:
            raise RuntimeError("Gemini client is not configured or failed to initialize.")

        prompt_parts: List[str] = []
        if system:
            prompt_parts.append(f"System: {system}\n")

        for m in messages:
            role = "User" if m.get("role") == "user" else "Assistant"
            prompt_parts.append(f"{role}: {m.get('content', '')}")

        full_content = "\n\n".join(prompt_parts)
        target_model = model or self.get_default_model()
        response = self._client.models.generate_content(  # pyright: ignore[reportUnknownMemberType]
            model=target_model,
            contents=full_content,
        )
        return (response.text or "").strip()

