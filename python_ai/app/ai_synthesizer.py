import logging
from typing import Any, Dict, List, Optional
from python_ai.app.config import settings
from python_ai.app.providers.registry import registry

logger = logging.getLogger(__name__)


class AISynthesizer:
    def __init__(self):
        self.registry = registry

    def synthesize_answer(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not documents:
            return {
                "answer": "No relevant web pages could be scraped for this query.",
                "sources": [],
                "confidence": "low",
            }

        context_parts: List[str] = []
        sources: List[Dict[str, Any]] = []
        for idx, doc in enumerate(documents[:5], 1):
            title = doc.get("title", f"Source {idx}")
            url = doc.get("url", "")
            text = doc.get("text", doc.get("snippet", ""))[:2500]
            summary = doc.get("snippet") or text[:280]
            sources.append({
                "id": idx,
                "title": title,
                "url": url,
                "summary": summary,
                "provider": doc.get("provider", ""),
                "collected_at": doc.get("collected_at", ""),
            })
            context_parts.append(f"--- SOURCE [{idx}]: {title} ({url}) ---\n{text}\n")

        context_text = "\n".join(context_parts)

        active_provider = self.registry.get_provider(provider)
        if active_provider:
            try:
                system_prompt = (
                    "You are an expert AI research assistant. Your task is to synthesize answers "
                    "strictly based on scraped web content. Cite sources using [1], [2], etc., and "
                    "clearly highlight key facts, takeaways, and nuances."
                )
                prompt = (
                    f"User Query: {query}\n\n"
                    f"Scraped web content:\n{context_text}\n\n"
                    f"Instructions:\n"
                    f"1. Synthesize a comprehensive, accurate answer to the query based on the sources.\n"
                    f"2. Cite sources using [1], [2], etc.\n"
                    f"3. Highlight key facts and takeaways."
                )
                answer_text = active_provider.generate(
                    prompt=prompt,
                    system=system_prompt,
                    model=model,
                )
                if answer_text:
                    return {
                        "answer": answer_text,
                        "sources": sources,
                        "provider_used": active_provider.name,
                        "model_used": model or active_provider.get_default_model(),
                        "confidence": "high",
                    }
            except Exception as e:
                logger.error(
                    "Error during AI synthesis with provider '%s': %s",
                    active_provider.name,
                    e,
                )

        return self._heuristic_synthesis(query, documents, sources)

    def format_news_feed(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        for art in articles:
            summary = art.get("snippet") or ""
            text = art.get("text") or ""
            if not summary and text:
                summary = text[:200] + "..."

            formatted.append({
                "title": art.get("title", "Untitled News"),
                "url": art.get("url", ""),
                "summary": summary,
                "author": art.get("author"),
                "published_date": art.get("date"),
                "source": art.get("source", "Web"),
                "image": art.get("image", ""),
            })
        return formatted

    def _heuristic_synthesis(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        summary_lines = [f"### Findings for: '{query}'\n"]

        for idx, doc in enumerate(documents[:5], 1):
            title = doc.get("title", f"Source {idx}")
            url = doc.get("url", "")
            snippet = doc.get("snippet") or (doc.get("text", "")[:280] + "...")
            summary_lines.append(f"- **[{title}]({url})** [Source {idx}]:\n  {snippet}\n")

        return {
            "answer": "\n".join(summary_lines),
            "sources": sources,
            "provider_used": "heuristic",
            "model_used": "extractor",
            "confidence": "medium",
        }


ai_synthesizer = AISynthesizer()
