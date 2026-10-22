import logging
import re
import time
from typing import Any, Dict, List, Optional

from python_ai.app.config import settings
from python_ai.app.providers.registry import registry
from python_ai.app.searcher import search_engine

logger = logging.getLogger(__name__)


class _Session:
    def __init__(self, session_id: str, mode: str, site_context: str):
        self.session_id = session_id
        self.mode = mode
        self.site_context = site_context
        self.history: List[Dict[str, str]] = []
        self.last_active = time.monotonic()

    def add(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        max_turns = settings.chat_history_max_turns
        if len(self.history) > max_turns * 2:
            self.history = self.history[-(max_turns * 2):]
        self.last_active = time.monotonic()

    def is_expired(self) -> bool:
        ttl = settings.chat_session_ttl_min * 60
        return time.monotonic() - self.last_active > ttl


_sessions: Dict[str, _Session] = {}


def _get_session(session_id: str, mode: str = "general", site_context: str = "") -> _Session:
    for sid in list(_sessions.keys()):
        if _sessions[sid].is_expired():
            del _sessions[sid]

    if session_id not in _sessions:
        _sessions[session_id] = _Session(session_id, mode, site_context)
    else:
        sess = _sessions[session_id]
        if site_context:
            sess.site_context = site_context
    return _sessions[session_id]


_CRYPTO_COINS = {
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "bnb", "xrp",
    "ripple", "doge", "dogecoin", "cardano", "ada", "polkadot", "dot",
    "avalanche", "avax", "chainlink", "link", "litecoin", "ltc", "shib",
    "shiba", "usdt", "usdc", "tron", "trx", "uniswap", "uni", "cosmos", "atom",
}
_SEARCH_KEYWORDS = re.compile(
    r"\b(what is|tell me about|explain|latest|news|price|how much|current|search|find|look up)\b",
    re.I,
)


def _needs_search(message: str) -> bool:
    return bool(_SEARCH_KEYWORDS.search(message))


def _detect_coin(message: str) -> Optional[str]:
    msg_lower = message.lower()
    for coin in _CRYPTO_COINS:
        if re.search(rf"\b{re.escape(coin)}\b", msg_lower):
            return coin
    return None


def _ai_chat(
    session: _Session,
    user_message: str,
    extra_context: str = "",
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    active_provider = registry.get_provider(provider)
    if not active_provider:
        return None

    try:
        system_parts = [
            "You are a helpful assistant embedded in an internet scraper bot.",
        ]
        if session.mode == "nav" and session.site_context:
            system_parts.append(
                f"You are acting as a site navigation helper. "
                f"Site context: {session.site_context}. "
                f"Help users find pages, features, and information within this site."
            )
        if session.mode == "crypto":
            system_parts.append(
                "You are a crypto-aware assistant. When discussing coins, give informative "
                "analysis using the provided market data. Always include a disclaimer that "
                "this is not financial advice."
            )
        system_parts.append("Be concise, friendly, and accurate.")

        if extra_context:
            system_parts.append(f"\nRelevant live data:\n{extra_context}")

        system_text = "\n".join(system_parts)

        # Build turn list for chat
        messages: List[Dict[str, str]] = []
        for turn in session.history[-10:]:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_message})

        reply = active_provider.chat(
            messages=messages,
            system=system_text,
            model=model,
        )
        return reply.strip() if reply else None
    except Exception as e:
        logger.error("AI chat error using provider '%s': %s", active_provider.name, e)
        return None


_GREETINGS = {"hi", "hello", "hey", "howdy", "good morning", "good afternoon", "good evening"}
_FAREWELLS = {"bye", "goodbye", "see you", "see ya", "cya", "take care", "later"}


def _rule_response(session: _Session, message: str, extra_context: str = "") -> str:
    msg_l = message.strip().lower().rstrip("!?.")

    if msg_l in _GREETINGS:
        return "Hello. Ask me anything — I can search the web, get news, fetch crypto prices, or help you navigate a site."

    if msg_l in _FAREWELLS:
        return "Goodbye."

    if any(w in msg_l for w in ("who are you", "what are you", "your name", "what can you do")):
        caps = "search the internet, fetch live news, get real-time crypto signals, scrape any website, and answer questions"
        if session.mode == "nav" and session.site_context:
            caps = f"help you navigate this site and {caps}"
        return f"I am a web scraper and intelligence bot. I can {caps}."

    if session.mode == "nav" and session.site_context:
        ctx_lower = session.site_context.lower()
        words = msg_l.split()
        for word in words:
            if len(word) > 3 and word in ctx_lower:
                idx = ctx_lower.find(word)
                snippet = session.site_context[max(0, idx - 20):idx + 80]
                return f"Based on the site info: ...{snippet}..."
        return f"Here is the available site context:\n{session.site_context}"

    if extra_context:
        lines = extra_context.strip().split("\n")[:5]
        summary = "\n".join(f"- {l}" for l in lines if l.strip())
        return f"Web findings for your query:\n\n{summary}"

    return "No matching records found. Try rephrasing your search or using a specific coin name or URL."


def chat(
    message: str,
    session_id: str = "default",
    mode: str = "general",
    site_context: str = "",
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    session = _get_session(session_id, mode, site_context)
    session.add("user", message)

    extra_context = ""
    sources: List[Dict[str, str]] = []

    if mode == "crypto" or _detect_coin(message):
        coin = _detect_coin(message)
        if coin:
            from python_ai.app.crypto import get_coin
            coin_data = get_coin(coin)
            if coin_data:
                extra_context = (
                    f"Live data for {coin_data['name']} ({coin_data['symbol']}):\n"
                    f"  Price: ${coin_data['price_usd']:,.4f} USD\n"
                    f"  24h Change: {coin_data['change_24h_pct']:+.2f}%\n"
                    f"  7d Change: {coin_data.get('change_7d_pct', 'N/A')}\n"
                    f"  Signal: {coin_data['signal']}\n"
                    f"  Market Cap: ${coin_data['market_cap_usd']:,.0f}\n"
                    f"  Volume 24h: ${coin_data['volume_24h_usd']:,.0f}"
                )

    elif mode == "general" and _needs_search(message):
        try:
            results = search_engine.search_web(message, max_results=3)
            if results:
                parts: List[str] = []
                for r in results:
                    parts.append(f"{r['title']}: {r.get('snippet', '')[:200]}")
                    sources.append({"title": r["title"], "url": r["url"]})
                extra_context = "\n".join(parts)
        except Exception as e:
            logger.warning("Chat search error: %s", e)

    reply = _ai_chat(
        session,
        message,
        extra_context,
        provider=provider,
        model=model,
    )

    if not reply:
        reply = _rule_response(session, message, extra_context)

    session.add("assistant", reply)

    return {
        "reply": reply,
        "session_id": session_id,
        "mode": mode,
        "sources": sources,
        "history_length": len(session.history) // 2,
    }


def get_history(session_id: str) -> List[Dict[str, str]]:
    if session_id in _sessions:
        return _sessions[session_id].history
    return []


def clear_session(session_id: str) -> bool:
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False
