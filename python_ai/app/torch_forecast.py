"""Deterministic PyTorch forecasting with an enforced risk gate."""

from __future__ import annotations

import math
import random
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .market_baseline import Bar, FeatureRow, generate_features

try:
    import torch
    from torch import nn
except ImportError:  # Keep the rest of the service importable without the optional wheel.
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]


class TorchUnavailableError(RuntimeError):
    """Raised when a forecasting operation needs the PyTorch dependency."""


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str


@dataclass(frozen=True)
class Forecast:
    timestamp: str
    predicted_direction: int
    probabilities: tuple[float, float, float]
    confidence: float
    expected_return: float
    risk: RiskDecision


@dataclass(frozen=True)
class TorchForecastResult:
    model_version: str
    horizon: int
    train_rows: int
    test_rows: int
    accuracy: float
    baseline_accuracy: float
    forecasts: tuple[Forecast, ...]


def save_torch_result(path: str | Path, result: TorchForecastResult) -> None:
    """Persist model metadata, evaluation, uncertainty, and risk decisions."""
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS torch_model_versions (
                model_version TEXT PRIMARY KEY, horizon INTEGER NOT NULL,
                train_rows INTEGER NOT NULL, test_rows INTEGER NOT NULL,
                accuracy REAL NOT NULL, baseline_accuracy REAL NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS torch_forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_version TEXT NOT NULL, timestamp TEXT NOT NULL,
                predicted_direction INTEGER NOT NULL, probabilities_json TEXT NOT NULL,
                confidence REAL NOT NULL, expected_return REAL NOT NULL,
                risk_approved INTEGER NOT NULL, risk_reason TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT OR REPLACE INTO torch_model_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (result.model_version, result.horizon, result.train_rows, result.test_rows,
             result.accuracy, result.baseline_accuracy, datetime.now(timezone.utc).isoformat()),
        )
        connection.executemany(
            """INSERT INTO torch_forecasts
            (model_version, timestamp, predicted_direction, probabilities_json,
             confidence, expected_return, risk_approved, risk_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (result.model_version, forecast.timestamp, forecast.predicted_direction,
                 json.dumps(forecast.probabilities), forecast.confidence, forecast.expected_return,
                 int(forecast.risk.approved), forecast.risk.reason)
                for forecast in result.forecasts
            ],
        )


class RiskEngine:
    """Independent final authority for whether a model signal may be used."""

    def __init__(
        self,
        *,
        min_confidence: float = 0.55,
        max_volatility: float = 0.05,
        min_expected_return: float = 0.0,
    ) -> None:
        self.min_confidence = min_confidence
        self.max_volatility = max_volatility
        self.min_expected_return = min_expected_return

    def approve(
        self,
        *,
        confidence: float,
        expected_return: float,
        volatility: float,
        collected_at: str | None = None,
        now: datetime | None = None,
        max_age_seconds: float = 300.0,
    ) -> RiskDecision:
        if not math.isfinite(confidence) or confidence < self.min_confidence:
            return RiskDecision(False, "confidence_below_threshold")
        if not math.isfinite(expected_return) or expected_return < self.min_expected_return:
            return RiskDecision(False, "expected_return_below_threshold")
        if not math.isfinite(volatility) or volatility > self.max_volatility:
            return RiskDecision(False, "volatility_above_threshold")
        if collected_at:
            observed = datetime.fromisoformat(collected_at).astimezone(timezone.utc)
            reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
            if (reference - observed).total_seconds() > max_age_seconds:
                return RiskDecision(False, "data_stale")
        return RiskDecision(True, "approved")


def evaluate_torch(
    bars: Iterable[Bar],
    *,
    horizon: int = 1,
    lookback: int = 3,
    train_ratio: float = 0.7,
    cost_bps: float = 10.0,
    seed: int = 7,
    risk_engine: RiskEngine | None = None,
    epochs: int = 80,
) -> TorchForecastResult:
    if torch is None or nn is None:
        raise TorchUnavailableError("PyTorch is required for torch forecasting; install python_ai/requirements.txt")
    if horizon < 1 or not 0.0 < train_ratio < 1.0 or cost_bps < 0:
        raise ValueError("invalid horizon, train_ratio, or cost_bps")
    selected = sorted(list(bars), key=lambda bar: bar.timestamp)
    features = generate_features(selected, lookback=lookback)
    usable = [(row, selected.index(row.bar)) for row in features
              if selected.index(row.bar) + horizon < len(selected)]
    split = int(len(usable) * train_ratio)
    train, test = usable[:split], usable[split:]
    if not train or not test:
        raise ValueError("both chronological train and held-out test sets are required")
    cost = cost_bps / 10_000.0

    def target(item: tuple[FeatureRow, int]) -> int:
        row, index = item
        change = selected[index + horizon].close / row.bar.close - 1.0
        return 2 if change > cost else 0 if change < -cost else 1

    _seed_everything(seed)
    model = nn.Sequential(nn.Linear(3, 12), nn.Tanh(), nn.Linear(12, 3))
    optimizer = torch.optim.Adam(model.parameters(), lr=0.03)
    x_train = torch.tensor([_vector(row) for row, _ in train], dtype=torch.float32)
    y_train = torch.tensor([target(item) for item in train], dtype=torch.long)
    for _ in range(epochs):
        optimizer.zero_grad()
        loss = nn.functional.cross_entropy(model(x_train), y_train)
        loss.backward()
        optimizer.step()

    engine = risk_engine or RiskEngine()
    forecasts: list[Forecast] = []
    with torch.no_grad():
        probabilities = torch.softmax(model(torch.tensor(
            [_vector(row) for row, _ in test], dtype=torch.float32)), dim=1)
    for (row, index), values in zip(test, probabilities.tolist()):
        predicted_class = max(range(3), key=values.__getitem__)
        direction = (-1, 0, 1)[predicted_class]
        confidence = max(values)
        expected = (values[2] - values[0]) * abs(row.return_lookback) - cost
        risk = engine.approve(
            confidence=confidence,
            expected_return=expected,
            volatility=row.volatility,
        )
        forecasts.append(Forecast(row.bar.timestamp, direction, tuple(values),
                                  confidence, expected, risk))
    actual = [target(item) for item in test]
    accuracy = sum(f.predicted_direction == (-1, 0, 1)[a]
                   for f, a in zip(forecasts, actual)) / len(actual)
    baseline = [1 if row.return_lookback >= 0 else -1 for row, _ in test]
    baseline_accuracy = sum(p == (-1, 0, 1)[a] for p, a in zip(baseline, actual)) / len(actual)
    return TorchForecastResult(
        model_version=f"mlp-v1-seed-{seed}-h{horizon}-lb{lookback}",
        horizon=horizon,
        train_rows=len(train),
        test_rows=len(test),
        accuracy=accuracy,
        baseline_accuracy=baseline_accuracy,
        forecasts=tuple(forecasts),
    )


def _vector(row: FeatureRow) -> list[float]:
    return [row.return_1, row.return_lookback, row.volatility]


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
