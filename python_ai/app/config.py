import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    host: str = os.getenv("PYTHON_AI_HOST", "127.0.0.1")
    port: int = int(os.getenv("PYTHON_AI_PORT", "5000"))
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    default_model: str = os.getenv("DEFAULT_AI_MODEL", "gemini-2.5-flash")
    user_agent: str = os.getenv(
        "SCRAPER_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    search_providers: str = os.getenv("SEARCH_PROVIDERS", "duckduckgo")
    searxng_url: str = os.getenv("SEARXNG_URL", "")
    brave_search_api_key: str = os.getenv("BRAVE_SEARCH_API_KEY", "")
    search_timeout_sec: float = float(os.getenv("SEARCH_TIMEOUT_SEC", "12"))
    coingecko_api_key: str = os.getenv("COINGECKO_API_KEY", "")
    coingecko_timeout_sec: float = float(os.getenv("COINGECKO_TIMEOUT_SEC", "10"))
    chat_history_max_turns: int = int(os.getenv("CHAT_HISTORY_MAX_TURNS", "20"))
    chat_session_ttl_min: int = int(os.getenv("CHAT_SESSION_TTL_MIN", "60"))
    data_store_path: str = os.getenv("DATA_STORE_PATH", "data/collections.sqlite3")
    provider_retries: int = int(os.getenv("PROVIDER_RETRIES", "3"))
    data_freshness_sec: float = float(os.getenv("DATA_FRESHNESS_SEC", "300"))

settings = Settings()
