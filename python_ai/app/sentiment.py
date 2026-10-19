"""Market-news claims, point-in-time sentiment, and value testing.

The module deliberately uses only claims published and retrieved before a
market bar.  This makes the resulting feature safe to replay historically.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from urllib.parse import urlsplit
from typing import Any, Iterable

from python_ai.app.data_collection import normalize_timestamp

ALLOWED_SOURCE_SUFFIXES = (
    "polymarket.com",
    "kalshi.com",
    "coingecko.com",
    "binance.com",
    "coinbase.com",
    "kraken.com",
    "okx.com",
    "coindesk.com",
    "cointelegraph.com",
    "theblock.co",
    "cryptoslate.com",
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "finance.yahoo.com",
)

_POSITIVE = {
    "adoption": 1.0, "approval": 1.0, "bullish": 1.0, "gain": 0.7,
    "growth": 0.7, "inflow": 0.8, "launch": 0.5, "surge": 1.0,
    "upgrade": 0.6, "positive": 0.6, "rally": 0.9,
}
_NEGATIVE = {
    "ban": -1.0, "bearish": -1.0, "crash": -1.0, "decline": -0.7,
    "hack": -1.0, "loss": -0.7, "outflow": -0.8,
    "regulation": -0.3, "sell": -0.7, "warning": -0.6, "negative": -0.6,
}
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class MarketClaim:
    title: str
    text: str
    url: str
    source: str
    published_at: str
    retrieved_at: str
    sentiment: float
    relevance: float
    event_type: str
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class SentimentFeature:
    symbol: str
    timestamp: str
    sentiment: float
    article_count: int
    claim_count: int


@dataclass(frozen=True)
class SentimentValueTest:
    baseline_mean_net_return: float
    sentiment_mean_net_return: float
    baseline_accuracy: float
    sentiment_accuracy: float
    evaluated_predictions: int
    retained: bool


def is_allowed_source(url: str, allowed_suffixes: Iterable[str] = ALLOWED_SOURCE_SUFFIXES) -> bool:
    host = urlsplit(url).hostname
    if not host:
        return False
    host = host.lower().removeprefix("www.")
    return any(host == suffix or host.endswith("." + suffix) for suffix in allowed_suffixes)


def score_sentiment(text: str) -> float:
    tokens = _WORD.findall(text.lower())
    if not tokens:
        return 0.0
    score = sum(_POSITIVE.get(token, 0.0) + _NEGATIVE.get(token, 0.0) for token in tokens)
    return max(-1.0, min(1.0, score / max(3.0, len(tokens) ** 0.5)))


def extract_claims(
    records: Iterable[dict[str, Any]],
    *,
    retrieved_at: str | None = None,
    symbols: Iterable[str] = (),
    allowed_suffixes: Iterable[str] = ALLOWED_SOURCE_SUFFIXES,
) -> list[MarketClaim]:
    retrieval = normalize_timestamp(retrieved_at, default_now=True)
    assert retrieval is not None
    normalized_symbols = tuple(sorted({str(symbol).upper() for symbol in symbols if str(symbol).strip()}))
    claims: list[MarketClaim] = []
    for record in records:
        url = str(record.get("url") or "")
        published = normalize_timestamp(record.get("published_at", record.get("date")))
        if not url or published is None or not is_allowed_source(url, allowed_suffixes):
            continue
        title = str(record.get("title") or "").strip()
        text = " ".join(
            part for part in (title, str(record.get("snippet") or ""), str(record.get("text") or "")) if part
        )
        if not text:
            continue
        upper_text = text.upper()
        matched = tuple(symbol for symbol in normalized_symbols if symbol in upper_text)
        relevance = 1.0 if matched else 0.5
        lowered = text.lower()
        event_type = (
            "market_event" if any(word in lowered for word in ("approval", "ban", "hack", "launch", "upgrade"))
            else "market_commentary"
        )
        claims.append(MarketClaim(
            title=title,
            text=text,
            url=url,
            source=str(record.get("source") or urlsplit(url).hostname or "unknown"),
            published_at=published,
            retrieved_at=retrieval,
            sentiment=score_sentiment(text),
            relevance=relevance,
            event_type=event_type,
            symbols=matched,
        ))
    return claims


def align_features(
    claims: Iterable[MarketClaim],
    timestamps: Iterable[tuple[str, str]],
    *,
    half_life_hours: float = 24.0,
) -> list[SentimentFeature]:
    if half_life_hours <= 0:
        raise ValueError("half_life_hours must be positive")
    parsed_claims = list(claims)
    features: list[SentimentFeature] = []
    for symbol, timestamp in timestamps:
        point = _parse(timestamp)
        usable = []
        for claim in parsed_claims:
            published = _parse(claim.published_at)
            retrieved = _parse(claim.retrieved_at)
            if published <= point and retrieved <= point and (not claim.symbols or symbol.upper() in claim.symbols):
                age_hours = max(0.0, (point - published).total_seconds() / 3600)
                weight = 2 ** (-age_hours / half_life_hours) * claim.relevance
                usable.append((claim.sentiment, weight))
        weighted = sum(value * weight for value, weight in usable) / sum(weight for _, weight in usable) if usable else 0.0
        features.append(SentimentFeature(symbol, timestamp, weighted, len(usable), len(usable)))
    return features


def save_claims(path: str | Path, claims: Iterable[MarketClaim]) -> None:
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS market_sentiment_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, text TEXT NOT NULL,
                url TEXT NOT NULL, source TEXT NOT NULL, published_at TEXT NOT NULL,
                retrieved_at TEXT NOT NULL, sentiment REAL NOT NULL, relevance REAL NOT NULL,
                event_type TEXT NOT NULL, symbols_json TEXT NOT NULL)"""
            )
            connection.executemany(
                """INSERT INTO market_sentiment_claims
                (title, text, url, source, published_at, retrieved_at, sentiment, relevance, event_type, symbols_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (c.title, c.text, c.url, c.source, c.published_at, c.retrieved_at,
                     c.sentiment, c.relevance, c.event_type, json.dumps(c.symbols))
                    for c in claims
                ],
            )


def evaluate_sentiment_value(
    bars: Iterable[Any],
    claims: Iterable[MarketClaim],
    *,
    horizon: int = 1,
    lookback: int = 3,
    train_ratio: float = 0.7,
    cost_bps: float = 10.0,
) -> SentimentValueTest:
    from python_ai.app.market_baseline import evaluate_baseline, generate_features

    selected = sorted(list(bars), key=lambda bar: bar.timestamp)
    baseline = evaluate_baseline(selected, horizon=horizon, lookback=lookback, train_ratio=train_ratio, cost_bps=cost_bps)
    rows = generate_features(selected, lookback=lookback)
    feature_map = {(feature.symbol, feature.timestamp): feature for feature in align_features(
        claims, ((row.bar.symbol, row.bar.timestamp) for row in rows)
    )}
    split = baseline.train_rows
    test_rows = rows[split:]
    sentiment_returns: list[float] = []
    sentiment_hits: list[bool] = []
    for row in test_rows:
        start = selected.index(row.bar)
        if start + horizon >= len(selected):
            continue
        gross = selected[start + horizon].close / row.bar.close - 1.0
        feature = feature_map[(row.bar.symbol, row.bar.timestamp)]
        direction = 1 if feature.sentiment > 0 else -1 if feature.sentiment < 0 else (1 if row.return_lookback >= 0 else -1)
        target = 1 if gross > cost_bps / 10_000 else -1 if gross < -cost_bps / 10_000 else 0
        sentiment_returns.append(direction * gross - cost_bps / 10_000)
        sentiment_hits.append(direction == target)
    value = mean(sentiment_returns) if sentiment_returns else 0.0
    return SentimentValueTest(
        baseline_mean_net_return=baseline.mean_net_return,
        sentiment_mean_net_return=value,
        baseline_accuracy=baseline.accuracy,
        sentiment_accuracy=mean(sentiment_hits) if sentiment_hits else 0.0,
        evaluated_predictions=len(sentiment_returns),
        retained=value > baseline.mean_net_return and (mean(sentiment_hits) if sentiment_hits else 0.0) >= baseline.accuracy,
    )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
