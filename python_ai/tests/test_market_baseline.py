import tempfile
import unittest
from pathlib import Path

from python_ai.app.market_baseline import (
    Bar,
    evaluate_baseline,
    generate_features,
    load_bars,
    save_predictions,
)


def bars():
    return [
        Bar(
            timestamp=f"2026-01-{index:02d}T00:00:00+00:00",
            symbol="BTCUSDT",
            open=float(100 + index),
            high=float(101 + index),
            low=float(99 + index),
            close=float(100 + index),
            volume=1000.0,
        )
        for index in range(1, 15)
    ]


class TestMarketBaseline(unittest.TestCase):
    def test_features_and_chronological_holdout(self):
        rows = generate_features(bars(), lookback=3)
        self.assertEqual(rows[0].bar.timestamp, "2026-01-04T00:00:00+00:00")
        result = evaluate_baseline(bars(), horizon=2, lookback=3, train_ratio=0.5, cost_bps=10)
        self.assertEqual(result.train_rows, 4)
        self.assertEqual(result.test_rows, 5)
        self.assertTrue(all(p.timestamp >= result.predictions[0].timestamp for p in result.predictions))
        self.assertTrue(all(p.net_return < p.gross_return for p in result.predictions))

    def test_predictions_are_persisted(self):
        result = evaluate_baseline(bars(), horizon=1, lookback=2, train_ratio=0.5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.sqlite3"
            save_predictions(path, result)
            self.assertTrue(path.exists())

    def test_fixture_is_reproducible(self):
        fixture = Path(__file__).parent / "fixtures" / "btcusdt_sample.csv"
        result = evaluate_baseline(load_bars(fixture), horizon=2, lookback=3, train_ratio=0.5, cost_bps=10)
        self.assertEqual(result.train_rows, 4)
        self.assertEqual(result.test_rows, 5)
        self.assertAlmostEqual(result.mean_net_return, 0.0173517, places=5)

    def test_csv_loader_rejects_missing_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bars.csv"
            path.write_text("timestamp,symbol,close\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_bars(path)


if __name__ == "__main__":
    unittest.main()
