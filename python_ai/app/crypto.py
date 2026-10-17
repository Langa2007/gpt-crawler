import logging
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Optional, TypedDict, TypeVar, cast

import httpx

from python_ai.app.config import settings
from python_ai.app.data_collection import (
    CollectionMetadata,
    ProviderResponse,
    SnapshotStore,
    is_fresh,
    normalize_symbol,
    normalize_timestamp,
    request_with_retries,
)

logger = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
_HEADERS = {"accept": "application/json"}
_CACHE_TTL = 60
_COIN_LIST_TTL = 3600

T = TypeVar("T")


class Signal(TypedDict):
    signal: str
    color: str
    momentum_score: float
JsonObject = Mapping[str, Any]

_cache: dict[str, tuple[object, float]] = {}
_coin_list_cache: list[JsonObject] | None = None
_coin_list_ts: float = 0.0


def _cached(key: str, fetch_fn: Callable[[], T]) -> T:
    now = time.monotonic()
    cached = _cache.get(key)
    if cached is not None:
        val, ts = cached
        if now - ts < _CACHE_TTL:
            return cast(T, val)
    val = fetch_fn()
    _cache[key] = (val, now)
    return val


def _client() -> httpx.Client:
    headers = dict(_HEADERS)
    if settings.coingecko_api_key:
        headers["x-cg-pro-api-key"] = settings.coingecko_api_key
    return httpx.Client(timeout=settings.coingecko_timeout_sec, headers=headers)


def _as_mapping(value: object) -> JsonObject:
    if isinstance(value, Mapping):
        return cast(JsonObject, value)
    return {}


def _as_json_list(value: object) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [_as_mapping(item) for item in items]


def _json_object(response: httpx.Response) -> JsonObject:
    return _as_mapping(response.json())


def _json_list(response: httpx.Response) -> list[JsonObject]:
    return _as_json_list(response.json())


def _string(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _signal(change_24h: float, change_7d: Optional[float]) -> Signal:
    score = change_24h
    if change_7d is not None:
        score = change_24h * 0.6 + change_7d * 0.4

    if score >= 5:
        label, color = "STRONG BUY", "green"
    elif score >= 2:
        label, color = "BUY", "lightgreen"
    elif score <= -5:
        label, color = "STRONG SELL", "red"
    elif score <= -2:
        label, color = "SELL", "orange"
    else:
        label, color = "HOLD", "gray"

    return {"signal": label, "color": color, "momentum_score": round(score, 2)}


def _volatility_status(price: float, high_24h: float, low_24h: float) -> tuple[str, float]:
    if not price or not high_24h or not low_24h:
        return "unknown", 0.0
    range_pct = ((high_24h - low_24h) / price) * 100.0
    if range_pct >= 8.0:
        return "volatile", round(range_pct, 2)
    if range_pct >= 4.0:
        return "moderate", round(range_pct, 2)
    return "stable", round(range_pct, 2)


def _balance_signal_mix(signals: list[dict[str, Any]], target_count: int = 6) -> list[dict[str, Any]]:
    if target_count <= 0 or not signals:
        return []
    if len(signals) <= target_count:
        return signals

    volatile = sorted(
        [s for s in signals if s.get("volatility") == "volatile"],
        key=lambda x: x.get("score", 0),
        reverse=True,
    )
    safer = sorted(
        [s for s in signals if s.get("volatility") in {"moderate", "stable"}],
        key=lambda x: x.get("score", 0),
        reverse=True,
    )

    target_volatile = max(0, min(len(volatile), target_count // 2))
    target_safer = max(0, min(len(safer), target_count - target_volatile))
    balanced = volatile[:target_volatile] + safer[:target_safer]

    seen = {id(item) for item in balanced}
    for signal in sorted(signals, key=lambda x: x.get("score", 0), reverse=True):
        if len(balanced) >= target_count:
            break
        if id(signal) not in seen:
            balanced.append(signal)
            seen.add(id(signal))

    return balanced[:target_count]


def _format_coin(coin: JsonObject) -> dict[str, Any]:
    market = _as_mapping(coin.get("market_data"))
    current_usd = _optional_number(_as_mapping(market.get("current_price")).get("usd"))
    change_24h = _number(market.get("price_change_percentage_24h"))
    change_7d = _optional_number(market.get("price_change_percentage_7d"))
    change_1h = _optional_number(_as_mapping(market.get("price_change_percentage_1h_in_currency")).get("usd"))
    market_cap = _optional_number(_as_mapping(market.get("market_cap")).get("usd"))
    volume_24h = _optional_number(_as_mapping(market.get("total_volume")).get("usd"))
    high_24h = _optional_number(_as_mapping(market.get("high_24h")).get("usd"))
    low_24h = _optional_number(_as_mapping(market.get("low_24h")).get("usd"))
    ath = _optional_number(_as_mapping(market.get("ath")).get("usd"))
    atl = _optional_number(_as_mapping(market.get("atl")).get("usd"))
    image = _as_mapping(coin.get("image"))

    sig = _signal(change_24h, change_7d)

    return {
        "id": _string(coin.get("id")),
        "name": _string(coin.get("name")),
        "symbol": _string(coin.get("symbol")).upper(),
        "image": _string(image.get("small")),
        "price_usd": current_usd,
        "change_1h_pct": round(change_1h, 2) if change_1h is not None else None,
        "change_24h_pct": round(change_24h, 2),
        "change_7d_pct": round(change_7d, 2) if change_7d is not None else None,
        "high_24h_usd": high_24h,
        "low_24h_usd": low_24h,
        "market_cap_usd": market_cap,
        "volume_24h_usd": volume_24h,
        "ath_usd": ath,
        "atl_usd": atl,
        "signal": sig["signal"],
        "signal_color": sig["color"],
        "momentum_score": sig["momentum_score"],
        "last_updated": _string(coin.get("last_updated")),
        "disclaimer": "Signal based on momentum calculation. Not financial advice.",
    }


def _record_collection_error(provider: str, error: Exception) -> None:
    message = f"{provider}: {error}"
    _collection_errors.append(message)
    logger.error("Data provider %s failed: %s", provider, error)


def _harmonized_signal(analysis: dict[str, Any], direction: str) -> tuple[str, str]:
    score = float(analysis.get("score") or 0.0)
    if direction == "short":
        return ("STRONG SHORT", "red") if score >= 90 else ("SHORT", "orange")
    return ("STRONG BUY", "green") if score >= 90 else ("BUY", "lightgreen")


def _attach_futures_setup(data: dict[str, Any]) -> dict[str, Any]:
    symbol = str(data.get("symbol") or "").upper()
    if not symbol:
        return data

    matching_ticker = None
    for ticker in get_binance_futures_tickers():
        ticker_symbol = str(ticker.get("symbol") or "").upper()
        ticker_base = str(ticker.get("base") or "").upper()
        if ticker_symbol == f"{symbol}USDT" or ticker_base == symbol:
            matching_ticker = ticker
            break

    if matching_ticker is None:
        return data

    price = float(matching_ticker.get("price") or 0.0)
    high_24h = float(matching_ticker.get("high_24h") or 0.0)
    low_24h = float(matching_ticker.get("low_24h") or 0.0)
    change_pct = float(matching_ticker.get("change_pct") or 0.0)
    regime, funding_rate, candles = _get_analysis_context(matching_ticker["symbol"])
    direction = regime or ("short" if change_pct >= 0 else "long")
    analysis = _multi_factor_analysis(
        candles, direction, regime, funding_rate
    )
    signal, color = _harmonized_signal(analysis, direction)
    data["signal"] = signal
    data["signal_color"] = color
    data["momentum_score"] = analysis.get("score", 0.0)
    data["signal_confidence"] = round(float(analysis.get("score", 0.0)) / 110.0 * 100.0, 1)
    data["signal_source"] = "Binance multi-factor analysis"
    data["signal_agreement"] = True
    data["signal_status"] = "confirmed" if analysis.get("confirmed") else "provisional"
    data["analysis"] = {
        "rsi_1h": analysis.get("rsi"),
        "ema20": analysis.get("ema20"),
        "ema50": analysis.get("ema50"),
        "atr_pct": analysis.get("atr_pct"),
        "volume_ratio": analysis.get("volume_ratio"),
        "funding_rate_pct": analysis.get("funding_rate"),
        "macd": analysis.get("macd"),
        "trend": analysis.get("trend"),
        "market_regime": regime or "neutral",
        "factors": analysis.get("factors", {}),
        "reason": analysis.get("reason"),
    }
    setup = _calculate_futures_setup(
        price, high_24h, low_24h, change_pct, direction, analysis.get("atr")
    )
    volatility, volatility_pct = _volatility_status(price, high_24h, low_24h)

    data["futures_setup"] = {
        "symbol": matching_ticker["symbol"],
        "direction": direction,
        "entry": setup["entry"],
        "sl": setup["sl"],
        "tp1": setup["tp1"],
        "tp2": setup["tp2"],
        "tp3": setup["tp3"],
        "leverage": setup["leverage"],
        "risk_reward": setup["rr"],
        "risk_pct": setup["risk_pct"],
        "volatility": volatility,
        "volatility_pct": volatility_pct,
        "confirmation_score": analysis.get("score", 0.0),
        "signal_status": data["signal_status"],
        "confidence_pct": data["signal_confidence"],
        "rsi_1h": analysis.get("rsi"),
        "analysis_factors": analysis.get("factors", {}),
        "rationale": (
            "Multi-factor bearish confirmation; wait for a small retracement before entering."
            if direction == "short"
            else "Multi-factor bullish confirmation; wait for a bounce into the lower entry zone before entering."
        ),
    }
    return data


def get_coin(query: str) -> Optional[dict[str, Any]]:
    coin_id = _resolve_id(query)
    if not coin_id:
        return None

    def fetch() -> dict[str, Any]:
        with _client() as c:
            r = request_with_retries(c, "GET", f"{COINGECKO_BASE}/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                },
            )
            r.raise_for_status()
            return _attach_futures_setup(_format_coin(_json_object(r)))

    try:
        return _cached(f"coin:{coin_id}", fetch)
    except Exception as e:
        _record_collection_error("coingecko_coin", e)
        return None


def get_trending() -> list[dict[str, Any]]:
    def fetch() -> list[dict[str, Any]]:
        with _client() as c:
            r = request_with_retries(c, "GET", f"{COINGECKO_BASE}/search/trending",
                                     attempts=settings.provider_retries)
            items = _as_json_list(_json_object(r).get("coins"))
            results: list[dict[str, Any]] = []
            for entry in items[:7]:
                item = _as_mapping(entry.get("item"))
                results.append({
                    "id": _string(item.get("id")),
                    "name": _string(item.get("name")),
                    "symbol": _string(item.get("symbol")).upper(),
                    "image": _string(item.get("small")),
                    "market_cap_rank": _optional_int(item.get("market_cap_rank")),
                    "price_btc": _optional_number(item.get("price_btc")),
                })
            return results

    try:
        return _cached("trending", fetch)
    except Exception as e:
        _record_collection_error("coingecko_trending", e)
        return []


def get_market_overview(coins: Optional[list[str]] = None, limit: int = 10) -> list[dict[str, Any]]:
    params: dict[str, str | int] = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": min(limit, 25),
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "1h,24h,7d",
    }
    if coins:
        ids = _resolve_ids_bulk(coins)
        if ids:
            params["ids"] = ",".join(ids)

    def fetch() -> list[dict[str, Any]]:
        with _client() as c:
            r = request_with_retries(c, "GET", f"{COINGECKO_BASE}/coins/markets",
                                     params=params, attempts=settings.provider_retries)
            results: list[dict[str, Any]] = []
            for item in _json_list(r):
                change_24h = _number(item.get("price_change_percentage_24h"))
                change_7d = _optional_number(item.get("price_change_percentage_7d_in_currency"))
                sig = _signal(change_24h, change_7d)
                results.append({
                    "id": _string(item.get("id")),
                    "name": _string(item.get("name")),
                    "symbol": _string(item.get("symbol")).upper(),
                    "image": _string(item.get("image")),
                    "price_usd": _optional_number(item.get("current_price")),
                    "change_1h_pct": _optional_number(item.get("price_change_percentage_1h_in_currency")),
                    "change_24h_pct": round(change_24h, 2),
                    "change_7d_pct": round(change_7d, 2) if change_7d is not None else None,
                    "market_cap_usd": _optional_number(item.get("market_cap")),
                    "volume_24h_usd": _optional_number(item.get("total_volume")),
                    "high_24h_usd": _optional_number(item.get("high_24h")),
                    "low_24h_usd": _optional_number(item.get("low_24h")),
                    "signal": sig["signal"],
                    "signal_color": sig["color"],
                    "momentum_score": sig["momentum_score"],
                })
            return results

    try:
        cache_key = f"market:{'|'.join(sorted(coins or []))}:{limit}"
        return _cached(cache_key, fetch)
    except Exception as e:
        _record_collection_error("coingecko_market", e)
        return []


def _load_coin_list() -> list[JsonObject]:
    global _coin_list_cache, _coin_list_ts
    now = time.monotonic()
    if _coin_list_cache is not None and now - _coin_list_ts < _COIN_LIST_TTL:
        return _coin_list_cache
    try:
        with _client() as c:
            r = request_with_retries(c, "GET", f"{COINGECKO_BASE}/coins/list",
                                     attempts=settings.provider_retries)
            _coin_list_cache = _json_list(r)
            _coin_list_ts = now
    except Exception as e:
        logger.warning("Could not load CoinGecko coin list: %s", e)
        if _coin_list_cache is None:
            _coin_list_cache = []
    return _coin_list_cache


def _resolve_id(query: str) -> Optional[str]:
    q = query.strip().lower()
    coin_list = _load_coin_list()

    for coin in coin_list:
        coin_id = _string(coin.get("id"))
        if coin_id.lower() == q:
            return coin_id

    matches = [c for c in coin_list if _string(c.get("symbol")).lower() == q]
    if len(matches) == 1:
        return _string(matches[0].get("id")) or None

    prefer = {
        "btc": "bitcoin", "eth": "ethereum", "bnb": "binancecoin",
        "sol": "solana", "ada": "cardano", "xrp": "ripple",
        "doge": "dogecoin", "dot": "polkadot", "avax": "avalanche-2",
        "matic": "matic-network", "link": "chainlink", "ltc": "litecoin",
        "usdt": "tether", "usdc": "usd-coin", "shib": "shiba-inu",
        "trx": "tron", "uni": "uniswap", "atom": "cosmos",
    }
    if q in prefer:
        return prefer[q]
    if matches:
        return _string(matches[0].get("id")) or None

    for coin in coin_list:
        if _string(coin.get("name")).lower() == q:
            return _string(coin.get("id")) or None

    for coin in coin_list:
        if q in _string(coin.get("name")).lower():
            return _string(coin.get("id")) or None
    return None


def _resolve_ids_bulk(queries: list[str]) -> list[str]:
    return [rid for q in queries if (rid := _resolve_id(q))]


# ---------------------------------------------------------------------------
# Binance USDT-M Futures Screener
# ---------------------------------------------------------------------------

BINANCE_FUTURES_BASE = "https://fapi.binance.com/fapi/v1"
_FUTURES_CACHE_TTL = 60  # seconds

_futures_cache: tuple[list[dict[str, Any]], float] | None = None
_klines_cache: dict[str, tuple[dict[str, list[float]], float]] = {}
_funding_cache: tuple[dict[str, float], float] | None = None
_collection_errors: list[str] = []
_last_collection_at: str | None = None
_snapshot_store = SnapshotStore(settings.data_store_path)


def collection_status() -> dict[str, Any]:
    return {
        "collected_at": _last_collection_at,
        "errors": list(_collection_errors),
    }


def get_binance_futures_tickers() -> list[dict[str, Any]]:
    """Fetch all 24-h ticker stats from Binance USDT-M futures."""
    global _futures_cache  # noqa: PLW0603
    now = time.monotonic()
    if _futures_cache is not None:
        data, ts = _futures_cache
        if now - ts < _FUTURES_CACHE_TTL:
            return data

    global _last_collection_at  # noqa: PLW0603
    _collection_errors.clear()
    try:
        with httpx.Client(timeout=5) as client:
            resp = request_with_retries(
                client, "GET", f"{BINANCE_FUTURES_BASE}/ticker/24hr",
                attempts=settings.provider_retries,
            )
            raw = resp.json()
    except Exception as exc:  # noqa: BLE001
        _collection_errors.append(f"binance_futures: {exc}")
        logger.warning("Binance futures ticker fetch failed: %s", exc)
        return []

    tickers: list[dict[str, Any]] = []
    raw_list = cast(list[object], raw) if isinstance(raw, list) else []
    for item in raw_list:
        obj = _as_mapping(item)
        symbol = normalize_symbol(obj.get("symbol"))
        if not symbol.endswith("USDT"):
            continue
        try:
            source_timestamp = normalize_timestamp(obj.get("closeTime"))
            tickers.append(
                {
                    "symbol": symbol,
                    "base": normalize_symbol(symbol.removesuffix("USDT")),
                    "price": float(_string(obj.get("lastPrice")) or "0"),
                    "change_pct": float(_string(obj.get("priceChangePercent")) or "0"),
                    "high_24h": float(_string(obj.get("highPrice")) or "0"),
                    "low_24h": float(_string(obj.get("lowPrice")) or "0"),
                    "volume_usdt": float(_string(obj.get("quoteVolume")) or "0"),
                    "source_timestamp": source_timestamp,
                    "stale": not is_fresh(source_timestamp, settings.data_freshness_sec)
                    if source_timestamp
                    else True,
                }
            )
        except ValueError:
            continue

    _last_collection_at = datetime.now(timezone.utc).isoformat()
    response = ProviderResponse(
        records=tickers,
        metadata=CollectionMetadata(
            provider="binance_futures",
            collected_at=_last_collection_at,
            source_timestamp=tickers[0].get("source_timestamp") if tickers else None,
        ),
    )
    _snapshot_store.save(response)
    _futures_cache = (tickers, now)
    return tickers


def _get_funding_rates() -> dict[str, float]:
    global _funding_cache  # noqa: PLW0603
    now = time.monotonic()
    if _funding_cache is not None and now - _funding_cache[1] < _FUTURES_CACHE_TTL:
        return _funding_cache[0]
    try:
        with httpx.Client(timeout=4) as client:
            response = request_with_retries(
                client, "GET", f"{BINANCE_FUTURES_BASE}/premiumIndex",
                attempts=settings.provider_retries,
            )
            raw = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Binance funding fetch failed: %s", exc)
        return {}

    rates: dict[str, float] = {}
    if isinstance(raw, list):
        for item in cast(list[object], raw):
            obj = _as_mapping(item)
            symbol = _string(obj.get("symbol"))
            rate_text = _string(obj.get("lastFundingRate"))
            try:
                if symbol and rate_text:
                    rates[symbol] = float(rate_text)
            except ValueError:
                continue
    _funding_cache = (rates, now)
    return rates


def _calculate_futures_setup(
    price: float,
    high_24h: float,
    low_24h: float,
    change_pct: float,
    direction: str,
    atr: float | None = None,
) -> dict[str, Any]:
    """Compute entry, TP1-3, stop-loss, R:R ratio, and leverage tier."""

    # Tier-based leverage: majors (BTC/ETH) → 8-10x; alts → 3-5x
    leverage = 10 if change_pct < 20 and price > 1_000 else (8 if price > 100 else 5)

    if direction == "short":
        # Entry slightly below current price (wait for micro-pullback)
        entry = round(price * 0.998, 6)
        sl = round(max(high_24h * 1.005, entry + (atr * 1.5 if atr else 0.0)), 6)
        tp1 = round(entry - (atr * 2.0 if atr else entry * 0.035), 6)
        tp2 = round(entry - (atr * 3.5 if atr else entry * 0.07), 6)
        tp3 = round(entry - (atr * 5.0 if atr else entry * 0.12), 6)
    else:  # long
        entry = round(price * 1.002, 6)
        sl = round(min(low_24h * 0.995, entry - (atr * 1.5 if atr else 0.0)), 6)
        tp1 = round(entry + (atr * 2.0 if atr else entry * 0.035), 6)
        tp2 = round(entry + (atr * 3.5 if atr else entry * 0.07), 6)
        tp3 = round(entry + (atr * 5.0 if atr else entry * 0.12), 6)

    # Risk = |entry - sl| / entry, Reward = |tp1 - entry| / entry
    risk = abs(entry - sl) / entry if entry else 0.0
    reward = abs(tp1 - entry) / entry if entry else 0.0
    rr = round(reward / risk, 2) if risk > 0 else 0.0

    return {
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "leverage": leverage,
        "rr": rr,
        "risk_pct": round(risk * 100, 2),
    }


def _entry_is_still_live(price: float, entry: float, direction: str) -> bool:
    if not price or not entry:
        return False
    if direction == "short":
        # entry zone was a small pullback/retest; once price moves beyond ~0.8% above entry, it is stale
        return price <= entry * 1.008
    if direction == "long":
        # long entry zone was near support; once price drops more than ~0.8% below entry, it is stale
        return price >= entry * 0.992
    return True


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    gains = [max(change, 0.0) for change in changes[-period:]]
    losses = [max(-change, 0.0) for change in changes[-period:]]
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    if average_loss == 0:
        return 100.0 if average_gain else 50.0
    return 100.0 - (100.0 / (1.0 + average_gain / average_loss))


def _technical_confirmation(  # pyright: ignore[reportUnusedFunction]
    closes: list[float], volumes: list[float], direction: str
) -> tuple[bool, float, float]:
    if len(closes) < 16 or len(volumes) < 6:
        return False, 0.0, 50.0

    rsi = _rsi(closes)
    if rsi is None:
        return False, 0.0, 50.0
    average_volume = sum(volumes[-6:-1]) / 5
    volume_ratio = volumes[-1] / average_volume if average_volume > 0 else 0.0
    reversal = closes[-1] < closes[-2] if direction == "short" else closes[-1] > closes[-2]
    overextended = rsi >= 68.0 if direction == "short" else rsi <= 32.0
    confirmed = overextended and reversal and volume_ratio >= 1.05
    score = min(100.0, max(0.0, abs(rsi - 50.0) * 2.0 + min(volume_ratio, 2.0) * 15.0))
    return confirmed, round(score, 2), round(rsi, 2)


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    multiplier = 2.0 / (period + 1.0)
    average = sum(values[:period]) / period
    for value in values[period:]:
        average = (value - average) * multiplier + average
    return average


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period or len(highs) != len(closes) or len(lows) != len(closes):
        return None
    true_ranges = [
        max(highs[index] - lows[index], abs(highs[index] - closes[index - 1]), abs(lows[index] - closes[index - 1]))
        for index in range(1, len(closes))
    ]
    return sum(true_ranges[-period:]) / period


def _get_binance_klines(symbol: str) -> dict[str, list[float]]:
    cached = _klines_cache.get(symbol)
    now = time.monotonic()
    if cached is not None and now - cached[1] < _FUTURES_CACHE_TTL:
        return cached[0]

    try:
        with httpx.Client(timeout=4) as client:
            response = request_with_retries(
                client, "GET", f"{BINANCE_FUTURES_BASE}/klines",
                params={"symbol": symbol, "interval": "1h", "limit": 50},
                attempts=settings.provider_retries,
            )
            raw = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Binance futures klines fetch failed for %s: %s", symbol, exc)
        return {"opens": [], "highs": [], "lows": [], "closes": [], "volumes": []}

    candles: dict[str, list[float]] = {
        "opens": [], "highs": [], "lows": [], "closes": [], "volumes": []
    }
    if isinstance(raw, list):
        for row in cast(list[object], raw):
            if not isinstance(row, list):
                continue
            values = cast(list[object], row)
            if len(values) < 6:
                continue
            try:
                candles["opens"].append(float(cast(str | int | float, values[1])))
                candles["highs"].append(float(cast(str | int | float, values[2])))
                candles["lows"].append(float(cast(str | int | float, values[3])))
                candles["closes"].append(float(cast(str | int | float, values[4])))
                candles["volumes"].append(float(cast(str | int | float, values[5])))
            except (TypeError, ValueError):
                continue
    _klines_cache[symbol] = (candles, now)
    return candles


def _get_binance_klines_batch(symbols: list[str]) -> dict[str, dict[str, list[float]]]:
    unique_symbols = list(dict.fromkeys(symbols))
    if not unique_symbols:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(unique_symbols))) as executor:
        candles = executor.map(_get_binance_klines, unique_symbols)
    return dict(zip(unique_symbols, candles))


def _get_analysis_context(symbol: str) -> tuple[str | None, float | None, dict[str, list[float]]]:
    with ThreadPoolExecutor(max_workers=3) as executor:
        btc_future = executor.submit(_get_binance_klines, "BTCUSDT")
        funding_future = executor.submit(_get_funding_rates)
        symbol_future = executor.submit(_get_binance_klines, symbol)
        regime = _market_regime(btc_future.result())
        funding_rate = funding_future.result().get(symbol)
        candles = symbol_future.result()
    return regime, funding_rate, candles


def _multi_factor_analysis(
    candles: dict[str, list[float]],
    direction: str,
    market_regime: str | None = None,
    funding_rate: float | None = None,
) -> dict[str, Any]:
    opens = candles.get("opens", [])
    highs = candles.get("highs", [])
    lows = candles.get("lows", [])
    closes = candles.get("closes", [])
    volumes = candles.get("volumes", [])
    if len(closes) < 50 or min(len(opens), len(highs), len(lows), len(volumes)) < 50:
        return {"confirmed": False, "score": 0.0, "reason": "insufficient candle history"}

    rsi = _rsi(closes)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    atr = _atr(highs, lows, closes)
    if rsi is None or ema20 is None or ema50 is None or atr is None or closes[-1] <= 0:
        return {"confirmed": False, "score": 0.0, "reason": "indicator calculation unavailable"}

    average_volume = sum(volumes[-6:-1]) / 5
    volume_ratio = volumes[-1] / average_volume if average_volume > 0 else 0.0
    candle_range = highs[-1] - lows[-1]
    body_ratio = abs(closes[-1] - opens[-1]) / candle_range if candle_range > 0 else 0.0
    bearish_candle = closes[-1] < opens[-1] and (closes[-1] - lows[-1]) / candle_range <= 0.35 if candle_range > 0 else False
    bullish_candle = closes[-1] > opens[-1] and (highs[-1] - closes[-1]) / candle_range <= 0.35 if candle_range > 0 else False
    reversal = bearish_candle if direction == "short" else bullish_candle
    trend_aligned = (ema20 < ema50 and closes[-1] < ema20) if direction == "short" else (ema20 > ema50 and closes[-1] > ema20)
    macd_now = (_ema(closes, 12) or 0.0) - (_ema(closes, 26) or 0.0)
    macd_prev = (_ema(closes[:-1], 12) or 0.0) - (_ema(closes[:-1], 26) or 0.0)
    macd_aligned = macd_now < macd_prev if direction == "short" else macd_now > macd_prev
    regime_aligned = market_regime is None or market_regime == direction
    funding_aligned = funding_rate is None or (
        funding_rate > 0 if direction == "short" else funding_rate < 0
    )
    rsi_extreme = rsi >= 68.0 if direction == "short" else rsi <= 32.0
    volatility_pct = atr / closes[-1] * 100.0

    factors = {
        "rsi_extreme": rsi_extreme,
        "volume_surge": volume_ratio >= 1.05,
        "reversal_candle": reversal and body_ratio >= 0.45,
        "trend_aligned": trend_aligned,
        "macd_aligned": macd_aligned,
        "regime_aligned": regime_aligned,
        "funding_aligned": funding_aligned,
        "volatility_usable": 0.15 <= volatility_pct <= 6.0,
    }
    score = sum(weight for name, weight in {
        "rsi_extreme": 20,
        "volume_surge": 15,
        "reversal_candle": 15,
        "trend_aligned": 20,
        "macd_aligned": 15,
        "regime_aligned": 10,
        "funding_aligned": 10,
        "volatility_usable": 5,
    }.items() if factors[name])
    confirmed = all(factors.values())
    return {
        "confirmed": confirmed,
        "score": float(score),
        "rsi": round(rsi, 2),
        "ema20": round(ema20, 8),
        "ema50": round(ema50, 8),
        "atr": round(atr, 8),
        "atr_pct": round(volatility_pct, 2),
        "volume_ratio": round(volume_ratio, 2),
        "funding_rate": round(funding_rate * 100.0, 4) if funding_rate is not None else None,
        "macd": round(macd_now, 8),
        "trend": "bearish" if ema20 < ema50 else "bullish",
        "factors": factors,
        "reason": "confirmed multi-factor setup" if confirmed else "multi-factor confirmation failed",
    }


def _market_regime(candles: dict[str, list[float]]) -> str | None:
    closes = candles.get("closes", [])
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    if ema20 is None or ema50 is None:
        return None
    if ema20 < ema50 and closes[-1] < ema20:
        return "short"
    if ema20 > ema50 and closes[-1] > ema20:
        return "long"
    return None


def get_futures_signals(
    strategy: str = "short",
    min_volume: float = 15_000_000.0,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Screen Binance USDT-M futures for actionable setups.

    strategy:
      "short"    – coins that surged ≥8% in 24h and are near the 24h high
      "long"     – coins that dropped ≥8% in 24h and are near the 24h low
      "trending" – top gainers by absolute |change_pct|, mixed direction
    """
    tickers = get_binance_futures_tickers()
    results: list[dict[str, Any]] = []
    now_ts = time.time()
    with ThreadPoolExecutor(max_workers=2) as executor:
        regime_future = executor.submit(lambda: _market_regime(_get_binance_klines("BTCUSDT")))
        funding_future = executor.submit(_get_funding_rates)
        regime = regime_future.result()
        funding_rates = funding_future.result()

    eligible_tickers: list[dict[str, Any]] = []
    for ticker in tickers:
        price = ticker["price"]
        high_24h = ticker["high_24h"]
        low_24h = ticker["low_24h"]
        change_pct = ticker["change_pct"]
        if ticker["volume_usdt"] < min_volume or price <= 0 or high_24h <= 0 or low_24h <= 0:
            continue
        range_24h = high_24h - low_24h
        position = (price - low_24h) / range_24h if range_24h > 0 else 0.5
        if strategy == "short" and (change_pct < 5.0 or position < 0.70):
            continue
        if strategy == "long" and (change_pct > -5.0 or position > 0.30):
            continue
        if strategy == "trending" and abs(change_pct) < 5.0:
            continue
        ticker["_position_in_range"] = position
        eligible_tickers.append(ticker)

    eligible_tickers.sort(key=lambda item: (abs(item["change_pct"]), item["volume_usdt"]), reverse=True)
    analysis_tickers = eligible_tickers[: min(20, max(8, limit * 3))]
    candle_data = _get_binance_klines_batch([ticker["symbol"] for ticker in analysis_tickers])

    for t in analysis_tickers:
        price: float = t["price"]
        high_24h: float = t["high_24h"]
        low_24h: float = t["low_24h"]
        change_pct: float = t["change_pct"]
        volume_usdt: float = t["volume_usdt"]

        range_24h = high_24h - low_24h
        position_in_range = t["_position_in_range"] if range_24h > 0 else 0.5
        # 0 = near low, 1 = near high

        if strategy == "short":
            direction = "short"
        elif strategy == "long":
            direction = "long"
        else:  # trending
            direction = "short" if change_pct > 0 else "long"

        funding_rate = funding_rates.get(t["symbol"])
        analysis = _multi_factor_analysis(
            candle_data.get(t["symbol"], {"opens": [], "highs": [], "lows": [], "closes": [], "volumes": []}),
            direction,
            regime,
            funding_rate,
        )

        setup = _calculate_futures_setup(price, high_24h, low_24h, change_pct, direction, analysis.get("atr"))
        entry_live = _entry_is_still_live(price, setup["entry"], direction)

        score = round(
            abs(change_pct) * (1.0 - abs(position_in_range - 0.5))
            + analysis.get("score", 0.0) * 0.35,
            2,
        )

        volatility, volatility_pct = _volatility_status(price, high_24h, low_24h)

        results.append(
            {
                "symbol": t["symbol"],
                "base": t["base"],
                "direction": direction,
                "price": price,
                "change_pct": round(change_pct, 2),
                "volume_usdt": volume_usdt,
                "high_24h": high_24h,
                "low_24h": low_24h,
                "position_in_range": round(position_in_range * 100, 1),
                "score": round(score, 2),
                "confirmation_score": analysis.get("score", 0.0),
                "confidence_pct": round(float(analysis.get("score", 0.0)) / 110.0 * 100.0, 1),
                "signal_status": "confirmed" if analysis.get("confirmed") else "provisional",
                "rsi_1h": analysis.get("rsi"),
                "ema20": analysis.get("ema20"),
                "ema50": analysis.get("ema50"),
                "atr_pct": analysis.get("atr_pct"),
                "volume_ratio": analysis.get("volume_ratio"),
                "funding_rate_pct": analysis.get("funding_rate"),
                "macd": analysis.get("macd"),
                "trend": analysis.get("trend", "unknown"),
                "market_regime": regime or "neutral",
                "analysis_factors": analysis.get("factors", {}),
                "entry_live": entry_live,
                "risk_warning": (
                    "Setup is provisional; monitor before entering."
                    if not analysis.get("confirmed")
                    else "Confirmed multi-factor setup."
                ),
                "volatility": volatility,
                "volatility_pct": volatility_pct,
                "refreshed_at": now_ts,
                "expires_at": now_ts + 180,
                "is_stale": False,
                **setup,
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    if strategy == "short":
        results = _balance_signal_mix(results, target_count=min(limit, 6))
    return results[:limit]
