import tempfile
import unittest
from pathlib import Path

from python_ai.app.market_baseline import Bar
from python_ai.app.sentiment import (
    MarketClaim,
    align_features,
    evaluate_sentiment_value,
    extract_claims,
    is_allowed_source,
    save_claims,
)


class TestSentiment(unittest.TestCase):
    def test_claims_keep_source_timestamps_and_reject_unpermitted_urls(self):
        records = [
            {
                "title": "Bitcoin approval is bullish",
                "url": "https://www.coindesk.com/markets/story",
                "date": "2026-01-01T00:00:00Z",
                "snippet": "positive adoption growth",
            },
            {
                "title": "Untrusted article",
                "url": "https://example.test/story",
                "date": "2026-01-01T00:00:00Z",
            },
        ]
        claims = extract_claims(
            records,
            retrieved_at="2026-01-01T01:00:00Z",
            symbols=["BTCUSDT"],
        )
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].published_at, "2026-01-01T00:00:00+00:00")
        self.assertEqual(claims[0].retrieved_at, "2026-01-01T01:00:00+00:00")
        self.assertGreater(claims[0].sentiment, 0)
        self.assertTrue(is_allowed_source("https://kalshi.com/markets/btc"))

    def test_alignment_excludes_future_publications_and_retrievals(self):
        claims = [
            MarketClaim("past", "bullish gain", "https://binance.com/a", "binance",
                        "2026-01-01T00:00:00+00:00", "2026-01-01T00:30:00+00:00", 0.8, 1.0, "market_event", ("BTCUSDT",)),
            MarketClaim("future", "bullish gain", "https://binance.com/b", "binance",
                        "2026-01-01T02:00:00+00:00", "2026-01-01T02:01:00+00:00", 0.8, 1.0, "market_event", ("BTCUSDT",)),
        ]
        feature = align_features(claims, [("BTCUSDT", "2026-01-01T01:00:00+00:00")])[0]
        self.assertEqual(feature.article_count, 1)

    def test_claims_persist_and_value_test_can_retain_signal(self):
        claim = MarketClaim("bullish", "bullish rally", "https://polymarket.com/event/btc", "polymarket",
                            "2026-01-04T00:00:00+00:00", "2026-01-04T00:01:00+00:00", 1.0, 1.0, "market_commentary", ("BTCUSDT",))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sentiment.sqlite3"
            save_claims(path, [claim])
            self.assertTrue(path.exists())
        bars = [
            Bar(f"2026-01-{index:02d}T00:00:00+00:00", "BTCUSDT", 100 + index, 101 + index, 99 + index, 100 + index, 1000)
            for index in range(1, 15)
        ]
        result = evaluate_sentiment_value(bars, [claim], horizon=1, lookback=3, train_ratio=0.5)
        self.assertEqual(result.evaluated_predictions, 5)
        self.assertIsInstance(result.retained, bool)


if __name__ == "__main__":
    unittest.main()
