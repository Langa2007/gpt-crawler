import logging
from typing import Any, Dict, List, Optional
import httpx
from python_ai.app.config import settings
from python_ai.app.providers.base import BaseAIProvider

logger = logging.getLogger(__name__)


class KimiProvider(BaseAIProvider):
    name = "kimi"

    def is_configured(self) -> bool:
        return bool(settings.kimi_api_key and settings.kimi_api_key.strip())

    def get_default_model(self) -> str:
        return settings.kimi_model or "moonshot-v1-8k"

    def _get_endpoint(self) -> str:
        base = (settings.kimi_api_base or "https://api.moonshot.cn/v1").rstrip("/")
        if not base.endswith("/chat/completions"):
            return f"{base}/chat/completions"
        return base

    def _call_completions(self, payload: Dict[str, Any]) -> str:
        url = self._get_endpoint()
        headers = {
            "Authorization": f"Bearer {settings.kimi_api_key.strip()}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=settings.ai_timeout_sec) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                raise RuntimeError(f"Moonshot Kimi API error ({resp.status_code}): {resp.text}")
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return ""
            msg = choices[0].get("message", {})
            return (msg.get("content") or "").strip()

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        if not self.is_configured():
            raise RuntimeError("Moonshot Kimi provider is not configured (missing KIMI_API_KEY).")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model or self.get_default_model(),
            "messages": messages,
            "max_tokens": max_tokens,
        }
        return self._call_completions(payload)

    def chat(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        if not self.is_configured():
            raise RuntimeError("Moonshot Kimi provider is not configured (missing KIMI_API_KEY).")

        formatted_msgs = []
        if system:
            formatted_msgs.append({"role": "system", "content": system})
        for m in messages:
            formatted_msgs.append({
                "role": m.get("role", "user"),
                "content": m.get("content", ""),
            })

        payload = {
            "model": model or self.get_default_model(),
            "messages": formatted_msgs,
            "max_tokens": max_tokens,
        }
        return self._call_completions(payload)

