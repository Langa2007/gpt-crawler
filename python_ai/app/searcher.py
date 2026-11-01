import logging
from html import unescape
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from python_ai.app.config import settings
from python_ai.app.data_collection import normalize_timestamp, request_with_retries

try:
    from ddgs import DDGS  # pyright: ignore[reportUnknownVariableType, reportMissingImports]
except ImportError:
    from duckduckgo_search import DDGS  # pyright: ignore[reportUnknownVariableType, reportMissingImports]

logger = logging.getLogger(__name__)

SEARCH_STOP_WORDS = {
    "about", "does", "happen", "is", "it", "the", "what", "when", "which",
    "who", "why", "how", "date", "day", "year", "tell", "me", "please",
}


class SearchEngine:
    def __init__(self) -> None:
        self.default_providers = self._provider_names(settings.search_providers)
        self.last_errors: list[str] = []
        self.last_collected_at: str | None = None

    def search_web(
        self, query: str, max_results: int = 5, providers: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        return self._search(query, max_results, "web", providers)

    def search_news(
        self,
        query: str,
        max_results: int = 10,
        timelimit: Optional[str] = "w",
        providers: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        return self._search(query, max_results, "news", providers, timelimit)

    def _search(
        self,
        query: str,
        max_results: int,
        search_type: str,
        providers: Optional[List[str]],
        timelimit: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        provider_names = self._provider_names(",".join(providers or self.default_providers))
        if not provider_names:
            provider_names = ["duckduckgo"]

        collected: List[Dict[str, Any]] = []
        self.last_errors = []
        self.last_collected_at = datetime.now(timezone.utc).isoformat()
        for name in provider_names:
            try:
                adapter = getattr(self, f"_search_{name}", None)
                if adapter is None:
                    logger.warning("Ignoring unsupported search provider: %s", name)
                    continue
                collected.extend(adapter(query, max_results, search_type, timelimit))
            except Exception as exc:
                message = f"{name}: {exc}"
                self.last_errors.append(message)
                logger.error("Search provider %s failed: %s", name, exc)
        return self._deduplicate(collected, max_results)

    def _search_duckduckgo(
        self, query: str, max_results: int, search_type: str, timelimit: Optional[str]
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        with DDGS() as ddgs:
            if search_type == "news":
                items = ddgs.news(query, max_results=max_results, timelimit=timelimit)
                for item in items:
                    results.append({
                        "title": item.get("title", ""), "url": item.get("url", ""),
                        "snippet": item.get("body", ""), "date": item.get("date", ""),
                        "source": item.get("source", "news"), "image": item.get("image", ""),
                        "provider": "duckduckgo",
                    })
            else:
                items = ddgs.text(query, max_results=max_results)
                for item in items:
                    results.append({
                        "title": item.get("title", ""), "url": item.get("href", ""),
                        "snippet": item.get("body", ""), "source": "web", "provider": "duckduckgo",
                    })
        return results

    def _search_searxng(
        self, query: str, max_results: int, search_type: str, timelimit: Optional[str]
    ) -> List[Dict[str, Any]]:
        if not settings.searxng_url:
            raise RuntimeError("SEARXNG_URL is not configured")
        endpoint = settings.searxng_url.rstrip("/") + "/search"
        params = {"q": query, "format": "json", "categories": "news" if search_type == "news" else "general"}
        if timelimit:
            params["time_range"] = {"d": "day", "w": "week", "m": "month"}.get(timelimit, timelimit)
        with httpx.Client(timeout=settings.search_timeout_sec, headers={"User-Agent": settings.user_agent}) as client:
            response = request_with_retries(client, "GET", endpoint, params=params, attempts=settings.provider_retries)
            payload = response.json()
        results: List[Dict[str, Any]] = []
        for item in payload.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""), "url": item.get("url", ""),
                "snippet": item.get("content", ""), "date": item.get("publishedDate", ""),
                "source": item.get("engine", "searxng"), "image": item.get("img_src", ""),
                "provider": "searxng",
            })
        return results

    def _search_wikipedia(
        self, query: str, max_results: int, search_type: str, timelimit: Optional[str]
    ) -> List[Dict[str, Any]]:
        if search_type == "news":
            return []
        topic_query = " ".join(
            word for word in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", query)
            if word.casefold() not in SEARCH_STOP_WORDS
        ).strip() or query
        with httpx.Client(
            timeout=settings.search_timeout_sec,
            headers={"User-Agent": settings.wikipedia_user_agent},
        ) as client:
            response = request_with_retries(
                client,
                "GET",
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "generator": "search",
                    "gsrnamespace": "0",
                    "gsrsearch": topic_query,
                    "gsrlimit": min(max_results, 20),
                    "prop": "extracts|info",
                    "exintro": "1",
                    "explaintext": "1",
                    "inprop": "url",
                    "format": "json",
                    "utf8": "1",
                },
                attempts=settings.provider_retries,
            )
            payload = response.json()

        results: List[Dict[str, Any]] = []
        for item in list(payload.get("query", {}).get("pages", {}).values())[:max_results]:
            page_id = item.get("pageid")
            if not page_id:
                continue
            results.append({
                "title": item.get("title", ""),
                "url": item.get("fullurl", f"https://en.wikipedia.org/?curid={page_id}"),
                "snippet": self._clean_wiki_text(unescape(item.get("extract", ""))),
                "source": "wikipedia",
                "provider": "wikipedia",
            })
        return results

    @staticmethod
    def _clean_wiki_text(value: str) -> str:
        text = re.sub(r"<ref[^>]*>.*?</ref>", " ", value, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
        text = re.sub(r"\[\[([^|\]]+\|)?([^\]]+)\]\]", r"\2", text)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _search_brave(
        self, query: str, max_results: int, search_type: str, timelimit: Optional[str]
    ) -> List[Dict[str, Any]]:
        if not settings.brave_search_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY is not configured")
        path = "news/search" if search_type == "news" else "web/search"
        headers = {"Accept": "application/json", "X-Subscription-Token": settings.brave_search_api_key}
        with httpx.Client(timeout=settings.search_timeout_sec, headers=headers) as client:
            response = request_with_retries(
                client, "GET", f"https://api.search.brave.com/res/v1/{path}",
                params={"q": query, "count": min(max_results, 20)},
                attempts=settings.provider_retries,
            )
            payload = response.json()
        records = payload.get("results", []) if search_type == "news" else payload.get("web", {}).get("results", [])
        return [{
            "title": item.get("title", ""), "url": item.get("url", ""),
            "snippet": item.get("description", ""),
            "date": normalize_timestamp(item.get("page_age", item.get("age", ""))),
            "source": "brave", "image": "", "provider": "brave",
        } for item in records[:max_results]]

    @staticmethod
    def _provider_names(value: str) -> List[str]:
        return [name.strip().lower() for name in value.split(",") if name.strip()]

    @staticmethod
    def _deduplicate(items: Iterable[Dict[str, Any]], max_results: int) -> List[Dict[str, Any]]:
        seen: Set[str] = set()
        results: List[Dict[str, Any]] = []
        by_provider: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            provider = str(item.get("provider") or "unknown")
            by_provider.setdefault(provider, []).append(item)

        while len(results) < max_results and by_provider:
            for provider in list(by_provider):
                provider_items = by_provider[provider]
                if not provider_items:
                    del by_provider[provider]
                    continue
                item = provider_items.pop(0)
                raw_url_val = item.get("url", "")
                if not isinstance(raw_url_val, str) or not raw_url_val:
                    continue
                parsed = urlsplit(raw_url_val)
                clean_url = urlunsplit((
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    urlencode([(k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith("utm_")]),
                    "",
                ))
                if clean_url in seen:
                    continue
                seen.add(clean_url)
                item["url"] = clean_url
                item["provider"] = provider
                item["collected_at"] = item.get("collected_at") or datetime.now(timezone.utc).isoformat()
                if item.get("date"):
                    item["date"] = normalize_timestamp(item["date"]) or item["date"]
                results.append(item)
                if len(results) >= max_results:
                    break
        return results


search_engine = SearchEngine()
