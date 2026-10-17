import unittest
from datetime import datetime, timezone
import tempfile
from pathlib import Path

from python_ai.app.market_baseline import Bar
from python_ai.app.torch_forecast import (
    RiskEngine, TorchUnavailableError, evaluate_torch, save_torch_result, torch,
)


def bars() -> list[Bar]:
    closes = [100, 101, 99, 102, 100, 103, 101, 104, 102, 105, 103, 106, 104, 107, 105, 108]
    return [
        Bar(f"2026-01-{i + 1:02d}T00:00:00+00:00", "BTCUSDT", c, c + 1, c - 1, c, 1000)
        for i, c in enumerate(closes)
    ]


@unittest.skipIf(torch is None, "PyTorch is not installed")
class TestTorchForecast(unittest.TestCase):
    def test_reproducible_and_compares_baseline(self):
        first = evaluate_torch(bars(), horizon=1, lookback=3, train_ratio=0.5)
        second = evaluate_torch(bars(), horizon=1, lookback=3, train_ratio=0.5)
        self.assertEqual(first, second)
        self.assertEqual(first.baseline_accuracy >= 0, True)
        self.assertTrue(all(len(f.probabilities) == 3 for f in first.forecasts))

    def test_risk_engine_suppresses_low_confidence_and_stale_data(self):
        engine = RiskEngine(min_confidence=0.9)
        self.assertFalse(engine.approve(confidence=0.5, expected_return=1, volatility=0).approved)
        old = "2020-01-01T00:00:00+00:00"
        decision = RiskEngine().approve(
            confidence=1, expected_return=1, volatility=0, collected_at=old,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertFalse(decision.approved)

    def test_result_persists_when_torch_is_available(self):
        result = evaluate_torch(bars())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecast.sqlite3"
            save_torch_result(path, result)
            self.assertTrue(path.exists())


class TestTorchDependency(unittest.TestCase):
    def test_missing_dependency_is_explicit(self):
        if torch is not None:
            self.skipTest("dependency is installed")
        with self.assertRaises(TorchUnavailableError):
            evaluate_torch(bars())
