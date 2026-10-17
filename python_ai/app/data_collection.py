from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)


def normalize_symbol(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum())


def normalize_timestamp(value: object, *, default_now: bool = False) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    if isinstance(value, str) and value.strip():
        raw = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat() if default_now else None


def is_fresh(timestamp: str | None, max_age_seconds: float, *, now: float | None = None) -> bool:
    if not timestamp:
        return False
    try:
        observed = datetime.fromisoformat(timestamp).timestamp()
    except ValueError:
        return False
    return 0 <= (time.time() if now is None else now) - observed <= max_age_seconds


@dataclass(frozen=True)
class CollectionMetadata:
    provider: str
    collected_at: str
    source_timestamp: str | None = None
    stale: bool = False


@dataclass
class ProviderResponse:
    records: list[dict[str, Any]]
    metadata: CollectionMetadata
    errors: list[str] = field(default_factory=list)


class DataProvider(Protocol):
    name: str

    def collect(self, query: str, limit: int) -> ProviderResponse:
        ...


def request_with_retries(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    attempts: int = 3,
    **kwargs: Any,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code not in {408, 425, 429} and response.status_code < 500:
                response.raise_for_status()
                return response
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            retry_after = 0.0
            if isinstance(exc, httpx.HTTPStatusError):
                retry_after = float(exc.response.headers.get("retry-after", 0) or 0)
            time.sleep(min(retry_after or 0.25 * (2**attempt), 2.0))
    raise RuntimeError(f"request failed after {attempts} attempts: {last_error}") from last_error


class SnapshotStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS collection_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    source_timestamp TEXT,
                    records_json TEXT NOT NULL
                )
                """
            )

    def save(self, response: ProviderResponse) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO collection_snapshots "
                "(provider, collected_at, source_timestamp, records_json) VALUES (?, ?, ?, ?)",
                (
                    response.metadata.provider,
                    response.metadata.collected_at,
                    response.metadata.source_timestamp,
                    json.dumps(response.records),
                ),
            )

    def latest(self, provider: str) -> ProviderResponse | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT collected_at, source_timestamp, records_json "
                "FROM collection_snapshots WHERE provider = ? "
                "ORDER BY id DESC LIMIT 1",
                (provider,),
            ).fetchone()
        if row is None:
            return None
        collected_at, source_timestamp, records_json = row
        return ProviderResponse(
            records=json.loads(records_json),
            metadata=CollectionMetadata(
                provider=provider,
                collected_at=collected_at,
                source_timestamp=source_timestamp,
            ),
        )
