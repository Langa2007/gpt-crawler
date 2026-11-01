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
        query_terms = self._terms(query)
        candidates: List[tuple[float, int, str, str]] = []
        date_pattern = re.compile(
            r"\b(?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+\d{1,2}(?:,?\s+\d{4})?\b|"
            r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
            r"September|October|November|December)(?:,?\s+\d{4})?\b",
            re.IGNORECASE,
        )

        for index, document in enumerate(documents[:5], 1):
            title = str(document.get("title", f"Source {index}"))
            text = str(document.get("text") or document.get("snippet") or "")
            title_terms = self._terms(title)
            for sentence in self._sentences(text):
                sentence_terms = self._terms(sentence)
                query_overlap = len(query_terms & sentence_terms)
                title_overlap = len(query_terms & title_terms)
                context_overlap = len(title_terms & sentence_terms)
                date_bonus = (
                    2
                    if date_pattern.search(sentence)
                    and (query_overlap > 0 or context_overlap > 0)
                    and re.search(r"\b(when|date|day|year)\b", query, re.IGNORECASE)
                    else 0
                )
                date_match = date_pattern.search(sentence)
                if (
                    date_match
                    and not re.search(r"\b\d{4}\b", date_match.group(0))
                    and re.search(r"\b(when|date|day)\b", query, re.IGNORECASE)
                ):
                    date_bonus += 2
                score = (
                    query_overlap * 4
                    + title_overlap * 2
                    + context_overlap
                    + date_bonus
                )
                if score > 0:
                    candidates.append((score, index, title, sentence))

        candidates.sort(key=lambda item: (-item[0], item[1]))
        selected: List[tuple[int, str, str]] = []
        seen_sentences: set[str] = set()
        minimum_score = candidates[0][0] - 2 if candidates else 0
        max_selected = 1 if re.search(
            r"\b(when|date|day|year)\b", query, re.IGNORECASE
        ) else 3
        for score, index, title, sentence in candidates:
            if score < minimum_score:
                continue
            key = sentence.casefold()
            if key in seen_sentences:
                continue
            seen_sentences.add(key)
            selected.append((index, title, sentence))
            if len(selected) == max_selected:
                break

        if selected:
            summary_lines = [f"### Answer for: '{query}'\n"]
            for index, title, sentence in selected:
                summary_lines.append(f"- {sentence} [Source {index}: {title}]")
        else:
            summary_lines = [f"### Findings for: '{query}'\n"]
            for index, document in enumerate(documents[:5], 1):
                title = document.get("title", f"Source {index}")
                text = document.get("text") or document.get("snippet") or ""
                summary_lines.append(f"- **[{title}]** [Source {index}]:\n  {text[:280]}...")

        return {
            "answer": "\n".join(summary_lines),
            "sources": sources,
            "provider_used": "heuristic",
            "model_used": "extractor",
            "confidence": "medium",
        }

    @staticmethod
    def _sentences(text: str) -> List[str]:
        return [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text)
            if sentence.strip()
        ]

    @staticmethod
    def _terms(text: str) -> set[str]:
        stop_words = {
            "about", "after", "also", "and", "are", "does", "for", "from",
            "have", "how", "into", "is", "that", "the", "this", "what",
            "when", "which", "who", "with", "would",
        }
        terms = set()
        for word in re.findall(r"[A-Za-z]{3,}", text.casefold()):
            if word in stop_words:
                continue
            normalized = re.sub(r"(ies|ing|ed|es|s)$", "", word)
            if len(normalized) > 5 and normalized.endswith("an"):
                normalized = normalized[:-2]
            elif len(normalized) > 4 and normalized.endswith("a"):
                normalized = normalized[:-1]
            terms.add(normalized)
        return terms


ai_synthesizer = AISynthesizer()
