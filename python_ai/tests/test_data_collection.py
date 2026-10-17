import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from python_ai.app.data_collection import (
    CollectionMetadata,
    ProviderResponse,
    SnapshotStore,
    is_fresh,
    normalize_symbol,
    normalize_timestamp,
    request_with_retries,
)


class TestDataCollection(unittest.TestCase):
    def test_symbols_and_timestamps_are_normalized(self):
        self.assertEqual(normalize_symbol(" btc/usdt "), "BTCUSDT")
        self.assertEqual(
            normalize_timestamp(1_700_000_000_000),
            "2023-11-14T22:13:20+00:00",
        )

    def test_freshness_rejects_future_and_old_data(self):
        timestamp = datetime.fromtimestamp(1_700_000_000, tz=timezone.utc).isoformat()
        self.assertTrue(is_fresh(timestamp, 60, now=1_700_000_030))
        self.assertFalse(is_fresh(timestamp, 60, now=1_700_000_061))
        self.assertFalse(is_fresh(timestamp, 60, now=1_699_999_999))

    def test_snapshot_store_round_trips_provider_response(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotStore(str(Path(directory) / "collections.sqlite3"))
            response = ProviderResponse(
                records=[{"symbol": "BTCUSDT", "price": 100}],
                metadata=CollectionMetadata(
                    provider="fixture",
                    collected_at="2026-10-17T08:00:00+00:00",
                ),
            )
            store.save(response)
            loaded = store.latest("fixture")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.records, response.records)

    def test_request_retries_transient_status(self):
        client = Mock()
        first = httpx.Response(503, request=httpx.Request("GET", "https://example.test"))
        second = httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.test"),
            content=json.dumps({"ok": True}).encode(),
        )
        client.request.side_effect = [first, second]
        with patch("python_ai.app.data_collection.time.sleep"):
            response = request_with_retries(client, "GET", "https://example.test", attempts=2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
