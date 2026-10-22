import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from python_ai.app.config import settings
from python_ai.app.searcher import search_engine
from python_ai.app.extractor import content_extractor
from python_ai.app.ai_synthesizer import ai_synthesizer
from python_ai.app.providers.registry import registry
from python_ai.app import chatbot as chatbot_module
from python_ai.app import crypto as crypto_module
from python_ai.app.sentiment import extract_claims, save_claims

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Internet Scraper Microservice", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchRequest(BaseModel):
    query: str
    max_results: int = 5
    type: str = "web"
    providers: Optional[List[str]] = None

class CleanHtmlRequest(BaseModel):
    html: str
    url: Optional[str] = None

class DocumentItem(BaseModel):
    title: Optional[str] = ""
    url: Optional[str] = ""
    text: Optional[str] = ""
    snippet: Optional[str] = ""

class SynthesizeRequest(BaseModel):
    query: str
    documents: List[DocumentItem]
    provider: Optional[str] = None
    model: Optional[str] = None

class NewsRequest(BaseModel):
    topic: str
    limit: int = 10
    timeframe: Optional[str] = "w"

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    mode: str = "general"
    site_context: Optional[str] = ""
    provider: Optional[str] = None
    model: Optional[str] = None

class ClearSessionRequest(BaseModel):
    session_id: str

class CryptoRequest(BaseModel):
    coin: str

class CryptoMarketRequest(BaseModel):
    coins: Optional[List[str]] = None
    limit: int = 10

class SentimentRequest(BaseModel):
    topic: str
    limit: int = 20
    timeframe: Optional[str] = "w"
    symbols: List[str] = []

@app.get("/health")
def health_check() -> Dict[str, Any]:
    active_prov = registry.get_active_provider_name()
    providers_info = registry.list_providers()
    return {
        "status": "healthy",
        "service": "python_ai",
        "version": "0.3.0",
        "active_provider": active_prov,
        "providers": providers_info,
        "gemini_configured": providers_info.get("gemini", {}).get("configured", False),
        "openai_configured": providers_info.get("openai", {}).get("configured", False),
        "claude_configured": providers_info.get("claude", {}).get("configured", False),
        "kimi_configured": providers_info.get("kimi", {}).get("configured", False),
        "qwen_configured": providers_info.get("qwen", {}).get("configured", False),
        "custom_configured": providers_info.get("custom", {}).get("configured", False),
    }

@app.post("/api/ai/search")
def search_internet(req: SearchRequest) -> Dict[str, Any]:
    if req.type == "news":
        results = search_engine.search_news(req.query, max_results=req.max_results, providers=req.providers)
    else:
        results = search_engine.search_web(req.query, max_results=req.max_results, providers=req.providers)
    return {
        "query": req.query,
        "type": req.type,
        "count": len(results),
        "results": results,
        "providers": req.providers or search_engine.default_providers,
        "collected_at": search_engine.last_collected_at,
        "errors": search_engine.last_errors,
    }

@app.post("/api/ai/clean-html")
def clean_html(req: CleanHtmlRequest) -> Dict[str, Any]:
    return content_extractor.extract_from_html(req.html, url=req.url)

@app.post("/api/ai/synthesize")
def synthesize_answer(req: SynthesizeRequest) -> Dict[str, Any]:
    doc_dicts = [doc.model_dump() for doc in req.documents]
    return ai_synthesizer.synthesize_answer(
        req.query,
        doc_dicts,
        provider=req.provider,
        model=req.model,
    )

@app.post("/api/ai/news")
def get_news(req: NewsRequest) -> Dict[str, Any]:
    raw_news = search_engine.search_news(req.topic, max_results=req.limit, timelimit=req.timeframe)
    formatted = ai_synthesizer.format_news_feed(raw_news)
    return {
        "topic": req.topic,
        "count": len(formatted),
        "articles": formatted,
        "collected_at": search_engine.last_collected_at,
        "errors": search_engine.last_errors,
    }

@app.post("/api/ai/market-sentiment")
def get_market_sentiment(req: SentimentRequest) -> Dict[str, Any]:
    raw_news = search_engine.search_news(req.topic, max_results=req.limit, timelimit=req.timeframe)
    claims = extract_claims(raw_news, retrieved_at=search_engine.last_collected_at, symbols=req.symbols)
    save_claims(settings.data_store_path, claims)
    return {
        "topic": req.topic,
        "count": len(claims),
        "claims": [claim.__dict__ for claim in claims],
        "collected_at": search_engine.last_collected_at,
        "errors": search_engine.last_errors,
    }

@app.post("/api/ai/chat")
def chat(req: ChatRequest) -> Dict[str, Any]:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")
    return chatbot_module.chat(
        message=req.message,
        session_id=req.session_id,
        mode=req.mode,
        site_context=req.site_context or "",
        provider=req.provider,
        model=req.model,
    )

@app.get("/api/ai/chat/history/{session_id}")
def chat_history(session_id: str) -> Dict[str, Any]:
    return {"session_id": session_id, "history": chatbot_module.get_history(session_id)}

@app.post("/api/ai/chat/clear")
def clear_chat(req: ClearSessionRequest) -> Dict[str, Any]:
    cleared = chatbot_module.clear_session(req.session_id)
    return {"cleared": cleared, "session_id": req.session_id}

@app.post("/api/ai/crypto")
def get_crypto(req: CryptoRequest) -> Dict[str, Any]:
    data = crypto_module.get_coin(req.coin)
    if not data:
        raise HTTPException(status_code=404, detail=f"Coin '{req.coin}' not found on CoinGecko")
    return {**data, "collection": crypto_module.collection_status()}

@app.get("/api/ai/crypto/trending")
def get_trending_crypto() -> Dict[str, Any]:
    return {"trending": crypto_module.get_trending(), "collection": crypto_module.collection_status()}

@app.post("/api/ai/crypto/market")
def get_market(req: CryptoMarketRequest) -> Dict[str, Any]:
    data = crypto_module.get_market_overview(coins=req.coins, limit=req.limit)
    return {"count": len(data), "coins": data, "collection": crypto_module.collection_status()}

@app.get("/api/ai/crypto/futures-signals")
def get_futures_signals(
    strategy: str = "short",
    limit: int = 10,
    min_volume: float = 15_000_000.0,
) -> Dict[str, Any]:
    signals = crypto_module.get_futures_signals(
        strategy=strategy, min_volume=min_volume, limit=limit
    )
    return {
        "count": len(signals),
        "strategy": strategy,
        "signals": signals,
        "collection": crypto_module.collection_status(),
    }

if __name__ == "__main__":
    uvicorn.run("python_ai.app.main:app", host=settings.host, port=settings.port, reload=True)
