import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    host: str = os.getenv("PYTHON_AI_HOST", "127.0.0.1")
    port: int = int(os.getenv("PYTHON_AI_PORT", "5000"))

    # Active AI provider: gemini | openai | claude | kimi | qwen | custom
    # If empty, the system auto-detects based on available API keys.
    ai_provider: str = os.getenv("AI_PROVIDER", "")
    default_model: str = os.getenv("DEFAULT_AI_MODEL", "gemini-2.5-flash")
    ai_timeout_sec: float = float(os.getenv("AI_TIMEOUT_SEC", "35.0"))

    # Google Gemini
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", os.getenv("DEFAULT_AI_MODEL", "gemini-2.5-flash"))

    # OpenAI / ChatGPT
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_api_base: str = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Anthropic Claude
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", os.getenv("CLAUDE_API_KEY", ""))
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

    # Moonshot Kimi
    kimi_api_key: str = os.getenv("KIMI_API_KEY", os.getenv("MOONSHOT_API_KEY", ""))
    kimi_api_base: str = os.getenv("KIMI_API_BASE", "https://api.moonshot.cn/v1")
    kimi_model: str = os.getenv("KIMI_MODEL", "moonshot-v1-8k")

    # Alibaba Qwen / DashScope
    qwen_api_key: str = os.getenv("QWEN_API_KEY", os.getenv("DASHSCOPE_API_KEY", ""))
    qwen_api_base: str = os.getenv("QWEN_API_BASE", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    qwen_model: str = os.getenv("QWEN_MODEL", "qwen-plus")

    # Custom / Local AI (Ollama, DeepSeek, Groq, vLLM, LM Studio)
    custom_ai_base_url: str = os.getenv("CUSTOM_AI_BASE_URL", "")
    custom_ai_api_key: str = os.getenv("CUSTOM_AI_API_KEY", "")
    custom_ai_model: str = os.getenv("CUSTOM_AI_MODEL", "")

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
