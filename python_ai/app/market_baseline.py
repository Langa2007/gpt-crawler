"""Reproducible chronological market baselines.

The baseline intentionally uses CSV input rather than live APIs. This makes
evaluation repeatable and prevents future information from leaking into the
held-out period.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Iterable


@dataclass(frozen=True)
class Bar:
    timestamp: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class FeatureRow:
    bar: Bar
    return_1: float
    return_lookback: float
    volatility: float


@dataclass(frozen=True)
class Prediction:
    symbol: str
    timestamp: str
    horizon: int
    predicted_direction: int
    target_direction: int
    gross_return: float
    net_return: float
    cost_bps: float
    features: dict[str, float]


@dataclass(frozen=True)
class BaselineResult:
    symbol: str
    horizon: int
    train_rows: int
    test_rows: int
    accuracy: float
    mean_net_return: float
    cumulative_net_return: float
    predictions: tuple[Prediction, ...]


def load_bars(path: str | Path) -> list[Bar]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        required = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
        missing = required - set(rows.fieldnames or ())
        if missing:
            raise ValueError(f"historical data is missing columns: {sorted(missing)}")
        bars = [
            Bar(
                timestamp=_timestamp(row["timestamp"]),
                symbol=row["symbol"].strip().upper(),
                open=_number(row["open"], "open"),
                high=_number(row["high"], "high"),
                low=_number(row["low"], "low"),
                close=_number(row["close"], "close"),
                volume=_number(row["volume"], "volume"),
            )
            for row in rows
        ]
    if not bars:
        raise ValueError("historical data contains no bars")
    return sorted(bars, key=lambda bar: (bar.symbol, bar.timestamp))


def generate_features(bars: Iterable[Bar], lookback: int = 3) -> list[FeatureRow]:
    if lookback < 1:
        raise ValueError("lookback must be positive")
    grouped = _group_bars(bars)
    features: list[FeatureRow] = []
    for symbol_bars in grouped.values():
        for index in range(lookback, len(symbol_bars)):
            current = symbol_bars[index]
            previous = symbol_bars[index - 1]
            anchor = symbol_bars[index - lookback]
            returns = [
                (symbol_bars[item].close / symbol_bars[item - 1].close) - 1.0
                for item in range(index - lookback + 1, index + 1)
            ]
            features.append(
                FeatureRow(
                    bar=current,
                    return_1=(current.close / previous.close) - 1.0,
                    return_lookback=(current.close / anchor.close) - 1.0,
                    volatility=pstdev(returns) if len(returns) > 1 else 0.0,
                )
            )
    return sorted(features, key=lambda row: (row.bar.symbol, row.bar.timestamp))


def evaluate_baseline(
    bars: Iterable[Bar],
    *,
    horizon: int = 1,
    lookback: int = 3,
    train_ratio: float = 0.7,
    cost_bps: float = 10.0,
    symbol: str | None = None,
) -> BaselineResult:
    if horizon < 1:
        raise ValueError("horizon must be positive")
    if not 0.0 < train_ratio < 1.0:
        raise ValueError("train_ratio must be between 0 and 1")
    if cost_bps < 0:
        raise ValueError("cost_bps cannot be negative")
    selected = [bar for bar in bars if symbol is None or bar.symbol == symbol]
    if not selected:
        raise ValueError("no bars available for the requested symbol")
    selected = sorted(selected, key=lambda bar: bar.timestamp)
    features = generate_features(selected, lookback=lookback)
    usable = [
        row for row in features
        if selected.index(row.bar) + horizon < len(selected)
    ]
    split = int(len(usable) * train_ratio)
    test = usable[split:]
    if not test:
        raise ValueError("held-out test set is empty")

    predictions: list[Prediction] = []
    for row in test:
        start = selected.index(row.bar)
        future = selected[start + horizon].close
        gross_return = (future / row.bar.close) - 1.0
        predicted = 1 if row.return_lookback >= 0 else -1
        net_return = predicted * gross_return - (cost_bps / 10_000.0)
        target = (
            1 if gross_return > (cost_bps / 10_000.0)
            else -1 if gross_return < -(cost_bps / 10_000.0)
            else 0
        )
        predictions.append(
            Prediction(
                symbol=row.bar.symbol,
                timestamp=row.bar.timestamp,
                horizon=horizon,
                predicted_direction=predicted,
                target_direction=target,
                gross_return=gross_return,
                net_return=net_return,
                cost_bps=cost_bps,
                features={
                    "return_1": row.return_1,
                    "return_lookback": row.return_lookback,
                    "volatility": row.volatility,
                },
            )
        )
    return BaselineResult(
        symbol=selected[0].symbol,
        horizon=horizon,
        train_rows=split,
        test_rows=len(predictions),
        accuracy=mean(p.predicted_direction == p.target_direction for p in predictions),
        mean_net_return=mean(p.net_return for p in predictions),
        cumulative_net_return=_compound(p.net_return for p in predictions),
        predictions=tuple(predictions),
    )


def save_predictions(path: str | Path, result: BaselineResult) -> None:
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS baseline_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    horizon INTEGER NOT NULL,
                    predicted_direction INTEGER NOT NULL,
                    target_direction INTEGER NOT NULL,
                    gross_return REAL NOT NULL,
                    net_return REAL NOT NULL,
                    cost_bps REAL NOT NULL,
                    features_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                )
                """
            )
            recorded_at = datetime.now(timezone.utc).isoformat()
            connection.executemany(
                """
                INSERT INTO baseline_predictions
                (symbol, timestamp, horizon, predicted_direction, target_direction,
                 gross_return, net_return, cost_bps, features_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        prediction.symbol,
                        prediction.timestamp,
                        prediction.horizon,
                        prediction.predicted_direction,
                        prediction.target_direction,
                        prediction.gross_return,
                        prediction.net_return,
                        prediction.cost_bps,
                        json.dumps(prediction.features, sort_keys=True),
                        recorded_at,
                    )
                    for prediction in result.predictions
                ],
            )


def result_as_dict(result: BaselineResult) -> dict[str, object]:
    return asdict(result)


def _group_bars(bars: Iterable[Bar]) -> dict[str, list[Bar]]:
    grouped: dict[str, list[Bar]] = {}
    for bar in bars:
        grouped.setdefault(bar.symbol, []).append(bar)
    for symbol_bars in grouped.values():
        symbol_bars.sort(key=lambda bar: bar.timestamp)
    return grouped


def _number(value: str, field: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"invalid {field} value: {value!r}") from error
    if number <= 0 and field in {"open", "high", "low", "close"}:
        raise ValueError(f"{field} must be positive")
    return number


def _timestamp(value: str) -> str:
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise ValueError(f"invalid timestamp: {value!r}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _compound(returns: Iterable[float]) -> float:
    compounded = 1.0
    for value in returns:
        compounded *= 1.0 + value
    return compounded - 1.0
