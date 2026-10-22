import logging
from typing import Any, Dict, List, Optional
import httpx
from python_ai.app.config import settings
from python_ai.app.providers.base import BaseAIProvider

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseAIProvider):
    name = "claude"

    def is_configured(self) -> bool:
        return bool(settings.anthropic_api_key and settings.anthropic_api_key.strip())

    def get_default_model(self) -> str:
        return settings.claude_model or "claude-3-5-sonnet-20241022"

    def _call_messages(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": settings.anthropic_api_key.strip(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Anthropic messages must alternate user / assistant and only support "user" and "assistant" roles.
        # Ensure role validity and avoid consecutive same-role messages if possible.
        claude_msgs: List[Dict[str, str]] = []
        for m in messages:
            role = "assistant" if m.get("role") == "assistant" else "user"
            content = m.get("content", "").strip()
            if not content:
                continue
            if claude_msgs and claude_msgs[-1]["role"] == role:
                claude_msgs[-1]["content"] += f"\n\n{content}"
            else:
                claude_msgs.append({"role": role, "content": content})

        if not claude_msgs:
            claude_msgs = [{"role": "user", "content": "Hello"}]

        payload: Dict[str, Any] = {
            "model": model or self.get_default_model(),
            "max_tokens": max_tokens,
            "messages": claude_msgs,
        }
        if system:
            payload["system"] = system

        with httpx.Client(timeout=settings.ai_timeout_sec) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                raise RuntimeError(f"Anthropic Claude API error ({resp.status_code}): {resp.text}")
            data = resp.json()
            content_list = data.get("content", [])
            text_parts = [item.get("text", "") for item in content_list if item.get("type") == "text"]
            return "\n".join(text_parts).strip()

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        if not self.is_configured():
            raise RuntimeError("Anthropic Claude provider is not configured (missing ANTHROPIC_API_KEY).")
        return self._call_messages(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            model=model,
            max_tokens=max_tokens,
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        if not self.is_configured():
            raise RuntimeError("Anthropic Claude provider is not configured (missing ANTHROPIC_API_KEY).")
        return self._call_messages(
            messages=messages,
            system=system,
            model=model,
            max_tokens=max_tokens,
        )

