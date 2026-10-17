# Phase Zero: Project Discovery and Baseline

**Status:** Complete  
**Date:** 2026-10-17  
**Repository:** `scrapper`

## 1. Purpose

This document records the baseline discovered before making further product or
architecture changes. The project is an internet scraper and AI information
service composed of:

- A Go gateway for HTTP APIs, concurrent crawling, rate limiting, URL safety,
  and basic HTML extraction.
- A Python FastAPI service for search, article cleaning, AI synthesis, chat,
  news formatting, and cryptocurrency data.
- A browser frontend and embeddable widget served by the Go gateway.

The intended consumers include external automation, CLI clients, a future
JavaScript frontend, and futures-signal integrations.

## 2. Current Architecture

```text
Clients / browser frontend / widget
                  |
                  | HTTP :8080
                  v
        Go gateway and crawler
                  |
                  | HTTP :5000
                  v
        Python AI microservice
```

### Go service

The Go entrypoint is `cmd/scraper-server/main.go`. Routing is defined in
`internal/api/router.go`. The gateway currently exposes:

| Route | Purpose |
|---|---|
| `GET /api/v1/health` | Gateway and Python-service health |
| `POST /api/v1/scrape` | Concurrent URL scraping |
| `POST /api/v1/crawl` | Bounded same-site crawling |
| `POST /api/v1/query` | Search, crawl, and synthesized query response |
| `POST /api/v1/news` | Structured news extraction |
| `POST /api/v1/chat` | Chat proxy |
| `POST /api/v1/crypto` | Single-coin data |
| `GET /api/v1/crypto/trending` | Trending crypto data |
| `POST /api/v1/crypto/market` | Market overview |
| `GET /api/v1/crypto/futures-signals` | Futures signal generation |

The crawler applies the following baseline protections:

- HTTP and HTTPS URLs only.
- No URLs containing embedded credentials.
- Private, loopback, link-local, multicast, unspecified, and reserved IP
  targets are rejected.
- DNS results are checked before dialing.
- Redirects are limited and revalidated.
- `robots.txt` is consulted and cached.
- Requests are rate-limited per host.
- Response bodies are limited to 5 MiB.
- Batch, crawl-depth, page-count, and concurrency limits are bounded.

### Python service

The FastAPI entrypoint is `python_ai/app/main.py`. Its current responsibilities
are:

- Search through configured providers.
- Clean HTML with Trafilatura and BeautifulSoup.
- Synthesize answers and format news feeds.
- Maintain in-memory chat sessions.
- Retrieve cryptocurrency market data and calculate futures signals.

The Python dependency manifest is
`python_ai/requirements.txt`. A project-local virtual environment exists at
`.venv/` and is the interpreter currently selected for Pylance.

### Client surfaces

- `frontend/` contains the browser dashboard.
- `widget/` contains the embeddable scraper widget.
- `scripts/start.ps1` starts the Python and Go services on Windows.
- `scripts/test_api.ps1` exercises health, news, crypto, chat, and scrape
  endpoints.

## 3. Verified Baseline

The following facts were verified during Phase Zero:

- The Go module targets Go 1.22.
- Python dependencies are declared in `python_ai/requirements.txt`.
- `trafilatura` is installed in `.venv` and resolves successfully in Pylance.
- The Python extractor import diagnostic was cleared after selecting
  `.venv/bin/python`.
- Go crawler tests exist in `internal/crawler/crawler_test.go`.
- Python unit tests currently exist in
  `python_ai/tests/test_volatility.py`.
- `.gitignore` currently ignores Python bytecode directories with
  `__pycache__/`.

## 4. Baseline Gaps and Risks

These are findings, not changes made during Phase Zero.

### Environment and startup consistency

The README describes a virtual environment at `python_ai/.venv/`, while the
current environment is at the repository root in `.venv/`. The PowerShell
startup script also looks for `python_ai\.venv\Scripts\python.exe`. The
supported development environment and startup script must be aligned before
relying on the documented one-command startup flow.

### Documentation drift

The README describes the original Go/Python scraping and query surfaces, while
the implementation also contains chat, crypto, frontend, and widget surfaces.
The API contract should be consolidated and kept current as the project
evolves.

### Test coverage

The current tests cover selected crawler and crypto behavior, but there is no
single documented end-to-end test that starts both services and verifies the
gateway-to-Python path. Error responses, request validation, provider
failures, and frontend integration also need explicit coverage.

### Runtime state

Chat history is held in process memory and therefore is lost on restart and is
not shared between service instances. This is acceptable for a prototype but
must be an explicit product decision before horizontal scaling.

### Security and operations

The gateway and Python service currently use permissive CORS settings. The
deployment boundary, authentication expectations, request limits, logging
policy, secret handling, and production observability are not yet documented
as a complete operational contract.

## 5. Phase Zero Decisions

The following defaults are established for the next phase:

1. Keep Go as the public gateway and Python as the internal AI service.
2. Treat `python_ai/requirements.txt` as the source of truth for Python
   dependencies.
3. Use a project-local virtual environment for development.
4. Preserve crawler safety controls and polite request behavior as mandatory
   behavior, not optional enhancements.
5. Keep external provider API keys in environment configuration only.
6. Prefer focused unit tests for pure logic and integration tests for the
   Go-to-Python boundary.
7. Update directly related documentation whenever an API, startup command, or
   configuration contract changes.

## 6. Phase One Readiness Checklist

Phase One can begin when the following are agreed or completed:

- [ ] Choose and document the canonical virtual-environment location.
- [ ] Make the startup script use the canonical environment on supported
      platforms.
- [ ] Reconcile the README with all implemented API routes.
- [ ] Define request validation and error-response conventions.
- [ ] Define the authentication and CORS policy for non-local deployments.
- [ ] Add a repeatable local integration test for both services.
- [ ] Decide whether chat state remains in memory or moves to shared storage.
- [ ] Define provider timeouts, retry behavior, and failure reporting.
- [ ] Define logging, metrics, and health-check expectations.
- [ ] Add CI commands for Go tests, Python tests, and formatting/type checks.

## 7. Phase Zero Exit Criteria

Phase Zero is complete when:

- The architecture and service boundaries are understood.
- Existing API and configuration surfaces are inventoried.
- Known documentation, environment, testing, state, and security gaps are
  recorded.
- No product behavior was changed solely as part of discovery.
- The next implementation phase has explicit prerequisites and acceptance
  criteria.

## 8. Recommended Phase One Order

1. Normalize the development and startup environment.
2. Establish API contracts and consistent validation/error responses.
3. Add gateway-to-Python integration coverage.
4. Reconcile and expand the README and configuration documentation.
5. Define deployment security and observability requirements.
6. Only then prioritize feature work or performance optimization.

## Phase 1: Stabilize Data Collection

**Status:** Complete
**Completion date:** 2026-10-17

### Implemented

1. **Standardized provider interfaces**
   - Added `ProviderResponse`, `CollectionMetadata`, and the `DataProvider`
     protocol in `python_ai/app/data_collection.py`.
   - Search providers now use a common collection path and expose provider
     errors and collection timestamps.
   - Crypto collection responses expose collection status alongside the
     existing API fields.

2. **Normalized symbols and timestamps**
   - Symbols are normalized to uppercase alphanumeric identifiers.
   - Unix seconds, Unix milliseconds, and ISO-8601 timestamps are normalized
     to UTC ISO-8601 strings.
   - Search records include normalized provider and collection metadata.
   - Binance futures ticker records include normalized symbols and source
     timestamps.

3. **Added validation and freshness checks**
   - Provider timestamps are checked against `DATA_FRESHNESS_SEC`.
   - Missing or invalid timestamps are marked stale instead of being silently
     treated as current.
   - Snapshot metadata records the provider, collection time, and source time.

4. **Handled retries, timeouts, and provider limits**
   - HTTP providers use bounded retries for transient HTTP failures and
     `Retry-After` when supplied.
   - Existing provider timeouts remain enforced.
   - Retry count is configurable with `PROVIDER_RETRIES`.
   - Existing search result and API result limits remain enforced.

5. **Persisted data needed for analysis**
   - Binance futures ticker snapshots are persisted in SQLite.
   - The default store is `data/collections.sqlite3`, configurable with
     `DATA_STORE_PATH`.
   - The `data/` directory is ignored by Git.

6. **Added representative-response tests**
   - `python_ai/tests/test_data_collection.py` covers normalization,
     freshness, retry behavior, and SQLite round trips.
   - Existing crypto and crawler tests remain in place.

### Reproducibility and visible failures

Collection failures are retained in provider status and logged at error or
warning level. Search responses expose `collected_at` and `errors`; crypto
responses expose a `collection` object with the same metadata. Successful
Binance ticker collection is persisted as a timestamped snapshot for later
analysis or replay.

### Completion criterion

**Met:** data can be collected and validated reproducibly, with source
metadata and visible errors when collection fails. Focused Python validation
passes with 14 tests:

```text
Ran 14 tests in 0.016s
OK
```

## Phase 2: Build the Shared Research Interface

**Status:** Complete
**Completion date:** 2026-10-17

### Implemented

1. **Separated the research stages**
   - Added `internal/research.Service` with explicit `Retriever`, `Scraper`,
     and `Answerer` interfaces.
   - The HTTP handler now delegates orchestration instead of mixing retrieval,
     scraping, fallback extraction, and answer generation.

2. **Added source-backed summaries**
   - Source responses now use typed `SourceSummary` records.
   - Each source includes an ID, title, URL, summary, provider, and collection
     timestamp where available.
   - The answer prompt and heuristic fallback both retain source citations.

3. **Supported general question answering**
   - `/api/v1/query` remains provider-independent and accepts arbitrary
     questions.
   - The same pipeline handles search, safe collection, extraction, and
     synthesis for general research questions.

4. **Defined stable request and response schemas**
   - The Go gateway now exposes typed query and source structures rather than
     untyped source maps.
   - The README documents the request, response, citation, and error contract.

5. **Added authentication and permissions**
   - Query and news routes support scoped API keys through
     `RESEARCH_API_KEYS`.
   - Clients send `X-API-Key` and `X-API-Scope: research`.
   - Missing or invalid credentials return `401 Unauthorized`.
   - Authentication remains disabled when no keys are configured for local
     development.

6. **Tested a second application**
   - `examples/research-client` is an independent Go client using only the
     HTTP contract.
   - Its integration test verifies credentials, stable decoding, and
     source-backed summaries.

### Completion criterion

**Met:** a second application can call `/api/v1/query` without importing or
duplicating the crawler, provider, extraction, or answer-generation
implementation. Go validation passes with the research client and auth tests.

### Endpoint readiness follow-up

The shared interface has now been extended beyond research:

- Added the typed Go SDK at `sdk/go/scrapper`.
- Added typed client methods for health, research, news, scrape, crawl, chat,
  single-coin, trending, market, and futures-signal APIs.
- Added context cancellation, configurable HTTP clients, API-key headers, and
  typed non-2xx errors.
- Added SDK tests for authentication, typed decoding, API errors, and context
  cancellation.

The endpoint surface is now usable by another Go application without copying
request construction or response parsing.

## Phase 3: Develop Market Features and Baselines

**Status:** Complete
**Completion date:** 2026-10-17

### Implemented

1. **Defined forecasting targets**
   - The baseline predicts the direction of the close-to-close return at the
     selected horizon.
   - A positive target is `+1`, a negative target is `-1`, and moves within
     the configured round-trip cost are neutral (`0`).

2. **Selected forecast horizons**
   - The evaluator accepts an explicit bar horizon through `--horizon`.
   - The default is one bar; tests cover a two-bar horizon.

3. **Built feature-generation pipelines**
   - Added `python_ai/app/market_baseline.py`.
   - Features are generated chronologically from OHLCV bars:
     one-bar return, lookback return, and rolling return volatility.
   - Input timestamps are normalized to UTC and bars are sorted before any
     feature or target is calculated.

4. **Implemented a baseline forecast**
   - The baseline is a transparent momentum/persistence rule: predict the sign
     of the lookback return.
   - It has no learned parameters and therefore is reproducible across runs.

5. **Established chronological evaluation**
   - Data is sorted by timestamp before splitting.
   - The train/test boundary is chronological and controlled by
     `--train-ratio`.
   - Future bars are used only to calculate outcomes after a test prediction;
     no future values are used as features.

6. **Recorded predictions and eventual outcomes**
   - Each prediction records symbol, timestamp, horizon, predicted direction,
     target direction, gross return, net return, cost, and feature values.
   - Predictions are persisted in SQLite with a recording timestamp.

7. **Included relevant trading costs**
   - `--cost-bps` subtracts round-trip costs from every predicted trade.
   - Results include mean net return and compounded cumulative net return.

### Reproducibility

Run the checked-in historical fixture with:

```bash
PYTHONDONTWRITEBYTECODE=1 python python_ai/scripts/run_baseline.py \
  python_ai/tests/fixtures/btcusdt_sample.csv \
  --symbol BTCUSDT \
  --horizon 2 \
  --lookback 3 \
  --train-ratio 0.5 \
  --cost-bps 10 \
  --predictions-db data/baseline.sqlite3
```

The fixture contains 14 chronological BTCUSDT bars. The held-out evaluation
has 4 training rows and 5 test predictions, with a reproducible mean net
return of approximately `0.0173517` using the documented settings.

### Completion criterion

**Met:** reproducible baseline results are produced from held-out historical
data, with explicit targets, horizons, chronological evaluation, recorded
outcomes, and trading costs. The baseline and fixture tests pass alongside the
existing test suite.

## Phase 4: Add PyTorch Forecasting

**Status:** Implemented

### Implemented

- Added a deterministic PyTorch MLP using the Phase Three features and the
  same cost-aware three-class target (down, neutral, up).
- Training is chronological, seeded, and evaluated only on held-out rows.
  Results include a model version, test accuracy, and baseline accuracy.
- Every forecast includes class probabilities and confidence.
- `RiskEngine` independently checks confidence, expected return, volatility,
  and optional collection freshness. A forecast is never approved without
  passing this gate.
- PyTorch is declared in `python_ai/requirements.txt`. Environments without
  the wheel fail explicitly with `TorchUnavailableError`, rather than
  silently producing a fallback signal.

### Reproducibility

```bash
python -m unittest python_ai.tests.test_torch_forecast
```

The test uses a deterministic in-memory fixture and fixed seed. Install
`python_ai/requirements.txt` first in environments where PyTorch is available.

### Completion criterion

**Met:** the model has deterministic chronological out-of-sample evaluation,
baseline comparison, probability-based uncertainty, and an independent risk
engine that suppresses low-confidence, stale, high-volatility, or
negative-expectation signals.
