import logging
import re
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
        direct_answer = self._date_question_answer(query, documents)
        if direct_answer:
            return {
                "answer": direct_answer,
                "sources": sources,
                "provider_used": "heuristic",
                "model_used": "extractor",
                "confidence": "medium",
            }

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

    @staticmethod
    def _date_question_answer(query: str, documents: List[Dict[str, Any]]) -> str:
        if not re.search(r"\b(when|date)\b", query, re.IGNORECASE):
            return ""

        query_words = {
            AISynthesizer._normalize_query_word(word)
            for word in re.findall(r"[A-Za-z]{4,}", query)
            if word.lower() not in {"when", "what", "date", "does", "happen"}
        }
        month = (
            r"(?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)"
        )
        date_pattern = re.compile(
            rf"\b(?:{month}\s+\d{{1,2}}|\d{{1,2}}\s+{month})(?:,?\s+\d{{4}})?\b",
            re.IGNORECASE,
        )
        candidates: List[tuple[int, str, str]] = []
        for document in documents:
            title = str(document.get("title", ""))
            text = str(document.get("text") or document.get("snippet") or "")
            haystack = f"{title} {text}"
            overlap = len(query_words & {
                AISynthesizer._normalize_query_word(word)
                for word in re.findall(r"[A-Za-z]{4,}", haystack)
            })
            for sentence in re.split(r"(?<=[.!?])\s+", text):
                match = date_pattern.search(sentence)
                if match:
                    candidates.append((overlap, match.group(0), sentence.strip()))
        if not candidates:
            return ""
        _, date, sentence = max(candidates, key=lambda item: item[0])
        return f"The date is **{date}**. {sentence}"

    @staticmethod
    def _normalize_query_word(word: str) -> str:
        normalized = word.lower()
        return {
            "kenyan": "kenya",
            "jamaican": "jamaica",
        }.get(normalized, normalized)


ai_synthesizer = AISynthesizer()
