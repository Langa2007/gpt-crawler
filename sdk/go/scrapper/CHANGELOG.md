# Changelog — Scrapper Go SDK

All notable changes to `github.com/Langa2007/scrapper/sdk/go/scrapper` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2026-10-27

### Added
- `NewClient(baseURL, apiKey string) *Client` — constructs a typed HTTP client for the Scrapper API. Defaults to `http://127.0.0.1:8080` when `baseURL` is empty.
- `WithHTTPClient(client *http.Client) *Client` — replaces the underlying HTTP transport (nil-safe no-op).
- `Health(ctx) (HealthResponse, error)` — `GET /api/v1/health`
- `Research(ctx, QueryRequest) (QueryResponse, error)` — `POST /api/v1/query`
- `News(ctx, NewsRequest) (NewsResponse, error)` — `POST /api/v1/news`
- `Scrape(ctx, ScrapeRequest) (ScrapeResponse, error)` — `POST /api/v1/scrape`
- `Crawl(ctx, CrawlRequest) (CrawlResponse, error)` — `POST /api/v1/crawl`
- `Chat(ctx, ChatRequest) (ChatResponse, error)` — `POST /api/v1/chat`
- `Crypto(ctx, CryptoRequest) (CryptoAsset, error)` — `POST /api/v1/crypto`
- `TrendingCrypto(ctx) (TrendingResponse, error)` — `GET /api/v1/crypto/trending`
- `CryptoMarket(ctx, CryptoMarketRequest) (CryptoMarketResponse, error)` — `POST /api/v1/crypto/market`
- `FuturesSignals(ctx, strategy, limit, minVolume) (FuturesSignalsResponse, error)` — `GET /api/v1/crypto/futures-signals`
- `*APIError` typed error with `StatusCode` and `Message`; compatible with `errors.As`.
- `NewsResponse.CollectedAt` and `NewsResponse.Errors` fields — aligned with server and OpenAPI contract.
- `FuturesSignalsResponse.Collection` field — aligned with server and OpenAPI contract.
- Zero external dependencies — uses only the Go standard library.
- Full unit test coverage for all 10 endpoints, authentication, context cancellation, custom HTTP clients, and error unwrapping.

### Notes
- The API gateway must be running separately. Installing this SDK does **not** install the Scrapper server.
- Research and news requests send `X-API-Key` and `X-API-Scope: research` automatically when a non-empty key is supplied to `NewClient`.

[0.1.0]: https://github.com/Langa2007/scrapper/releases/tag/sdk/go/scrapper/v0.1.0

