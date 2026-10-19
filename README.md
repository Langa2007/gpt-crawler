# AI Internet Scraper Bot (Go + Python)

An intelligent, high-throughput web scraping and AI information extraction bot combining **Go** (for concurrent crawling, rate limiting, and API gateway) and **Python** (for web searching, HTML readability cleaning, and LLM synthesis).

Designed to be consumed by external systems (such as **futures signals**), CLI scripts, or future JavaScript web frontends.

---

## Architecture Overview

```
+-------------------------------------------------------------+
|              Clients: scrapper / JS Frontend / CLI         |
+------------------------------+------------------------------+
                               |  HTTP REST (Port 8080)
                               v
+-------------------------------------------------------------+
|                   Go Core & API Gateway                     |
|  - Worker pool for high concurrency crawling                |
|  - Connection pooling & polite rate limiting                |
|  - Fast native HTML tokenization                            |
|  - CORS-enabled REST API                                    |
+------------------------------+------------------------------+
                               |  Internal HTTP (Port 5000)
                               v
+-------------------------------------------------------------+
|                  Python AI Microservice                     |
|  - Federated public-web search (DuckDuckGo, SearXNG, Brave) |
|  - HTML cleaning & boilerplate removal (Trafilatura & BS4)  |
|  - AI synthesis (Google Gemini, OpenAI, or heuristics)      |
|  - Structured news & content formatting                     |
+-------------------------------------------------------------+
```

---

## Directory Structure

```text
scrapper/
├── cmd/
│   └── scraper-server/
│       └── main.go                 # Go API Server entrypoint
├── internal/
│   ├── crawler/
│   │   ├── crawler.go              # High-concurrency worker pool
│   │   ├── extractor.go            # Native Go HTML cleaner
│   │   └── models.go               # Request/Response schemas
│   ├── service/
│   │   └── ai_client.go            # Go client for Python microservice
│   └── api/
│       ├── router.go               # Routes & CORS middleware
│       └── handlers.go             # Handlers for /health, /scrape, /news, /query
├── python_ai/
│   ├── app/
│   │   ├── main.py                 # FastAPI microservice
│   │   ├── searcher.py             # Web & News search provider
│   │   ├── extractor.py            # Trafilatura + BS4 article extractor
│   │   ├── ai_synthesizer.py       # LLM intelligence & news formatter
│   │   └── config.py               # Settings loader
│   ├── requirements.txt            # Python dependencies
│   └── .venv/                      # Python virtual environment
├── scripts/
│   ├── start.ps1                   # Windows startup script
│   ├── start.sh                    # Linux startup script
│   └── test_api.ps1                # Integration test script
├── .env.example                    # Environment template
├── .env                            # Local configuration
├── go.mod                          # Go module definition
└── README.md
```

---

## Quickstart Guide

### 1. Requirements
- **Python 3.10+**
- **Go 1.22+**
- **PyTorch 2.7+** for reproducible forecasting

On Linux, install Python 3, its virtual environment support, and Go using your
distribution's package manager. For example, on Debian or Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip golang-go
```

Create a project virtual environment and install the Python dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r python_ai/requirements.txt
```

The startup script also uses `.venv/bin/python` if it exists. If you prefer a
system Python installation, install the requirements with `python3 -m pip` and
ensure `python3` is available on your `PATH`.

The offline forecasting module is available as
`python_ai.app.torch_forecast.evaluate_torch`. It uses chronological
out-of-sample evaluation, reports class probabilities and confidence, compares
with the Phase Three baseline, and requires its independent `RiskEngine` before
a signal can be approved. Missing PyTorch is reported explicitly; no fallback
signal is generated.

Market sentiment is collected by the Python service at
`POST /api/ai/market-sentiment`. It accepts `topic`, `limit`, `timeframe`, and
optional `symbols`, then stores permitted prediction-market, exchange,
CoinGecko, and trading-news claims in the configured SQLite data store. Each
claim includes both `published_at` and `retrieved_at`. Historical alignment
rejects claims that were not available by the bar timestamp, and
`evaluate_sentiment_value` retains the feature only when held-out,
cost-aware mean return and accuracy both improve over the market baseline.

### 2. Configure Environment (Optional)
To enable generative AI reasoning with Google Gemini:
Edit `.env`:
```env
GEMINI_API_KEY="your-gemini-api-key-here"
```
*(If no API key is provided, the scraper operates using its built-in heuristic extraction algorithms).*

### 3. Run the Bot

#### Linux

From the project root, run:

```bash
./scripts/start.sh
```

If the script is not executable, run `chmod +x scripts/start.sh` once, then
run it again. It starts the Python AI service on port 5000 and the Go server,
which serves the frontend and API on port 8080. Open
<http://localhost:8080> in your browser. Port 5000 is an internal Python API;
opening it in a browser does not show the frontend.

To start the services manually, use two terminals from the project root.

**Terminal 1 (Python AI Microservice):**

```bash
. .venv/bin/activate
python -m uvicorn python_ai.app.main:app --host 127.0.0.1 --port 5000
```

**Terminal 2 (Go Gateway and frontend):**

```bash
go run ./cmd/scraper-server
```

#### Windows

Run the startup script in PowerShell:
```powershell
.\scripts\start.ps1
```

Or start the two services manually in separate terminals from the project root:
**Terminal 1 (Python AI Microservice):**
```powershell
cd python_ai
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5000
```

**Terminal 2 (Go Gateway):**
```powershell
go run ./cmd/scraper-server
```

The Go server serves the frontend at <http://localhost:8080> on both operating
systems. The Python service on port 5000 is for internal API calls.

---

## API Endpoints (Port 8080)

### Using the Go SDK

The API is language independent. Its complete REST contract is in
[OpenAPI format](sdk/openapi.yaml), which can be imported into client
generators for other languages or used directly with any HTTP library. See
[SDK and API contract guide](sdk/README.md).

Other Go projects can import the typed client:

```bash
go get github.com/Langa2007/scrapper/sdk/go/scrapper
```

Create a client with the API gateway URL, then call its methods with a
`context.Context`. For example:

```go
client := scrapper.NewClient("http://localhost:8080", "")
result, err := client.Research(ctx, scrapper.QueryRequest{
    Query: "Recent developments in renewable energy",
})
```

The SDK includes methods for health checks, research, news, scraping, crawling,
chat, and crypto endpoints. See [the Go SDK guide](sdk/go/scrapper/README.md)
for authentication, response types, and full usage details. The SDK sends
requests to the Go gateway on port 8080; port 5000 is the internal Python API.

### Research interface

The research interface separates retrieval, public-page scraping, content
extraction, and answer generation behind one stable endpoint. A client only
needs to send a question; it does not need to duplicate provider selection,
crawler safety, extraction, or citation logic.

`POST /api/v1/query`

Request:

```json
{
  "query": "What are the latest developments in quantum computing?",
  "max_results": 5,
  "providers": ["duckduckgo"]
}
```

Response:

```json
{
  "query": "What are the latest developments in quantum computing?",
  "answer": "Synthesized answer with citations [1], [2].",
  "confidence": "high",
  "providers": ["duckduckgo"],
  "duration_ms": 1420,
  "sources": [
    {
      "id": 1,
      "title": "Source 1",
      "url": "https://example.com/article",
      "summary": "Evidence used for the answer.",
      "provider": "duckduckgo",
      "collected_at": "2026-10-17T09:00:00+00:00"
    }
  ],
  "errors": []
}
```

`sources` is source-backed: every citation identifies the URL and includes the
summary supplied to answer generation. `errors` is present when one or more
providers fail, so clients can distinguish partial collection from a clean
result.

When `RESEARCH_API_KEYS` is configured, query and news requests require
`X-API-Key` and `X-API-Scope: research` headers. Configure keys as
`key:scope1|scope2,key2`. With no configured keys, local development remains
open.

### 1. News Extraction (For **Dira News** Integration)
Fetch structured news articles on any topic, ready to be ingested into Dira News.

- **URL:** `POST /api/v1/news`
- **Payload:**
```json
{
  "topic": "artificial intelligence breakthroughs",
  "limit": 5,
  "timeframe": "w"
}
```
- **Response:**
```json
{
  "topic": "artificial intelligence breakthroughs",
  "count": 5,
  "articles": [
    {
      "title": "Article Headline",
      "url": "https://example.com/article",
      "summary": "Summary or key takeaways from the article...",
      "author": "Author Name",
      "published_date": "2026-09-08",
      "source": "TechCrunch",
      "image": "https://example.com/image.jpg"
    }
  ]
}
```

### 2. Intelligent Internet Query
Ask any question. The bot searches the internet, crawls top pages, cleans boilerplate, and synthesizes an answer with citations.

- **URL:** `POST /api/v1/query`
- **Payload:**
```json
{
  "query": "What are the latest developments in quantum computing?",
  "max_results": 5
}
```
- **Response:**
```json
{
  "query": "What are the latest developments in quantum computing?",
  "answer": "Synthesized AI response with citations [1], [2]...",
  "sources": [
    { "id": 1, "title": "Source 1", "url": "https://..." },
    { "id": 2, "title": "Source 2", "url": "https://..." }
  ],
  "confidence": "high",
  "duration_ms": 1420
}
```

### 3. Direct Concurrent Web Scraping
Directly scrape public HTTP(S) URLs with Go's concurrent worker pool and Python's readability engine. Requests are bounded, rate-limited per host, checked against `robots.txt`, and protected from private-network targets.

- **URL:** `POST /api/v1/scrape`
- **Payload:**
```json
{
  "urls": [
    "https://news.ycombinator.com",
    "https://github.com/trending"
  ],
  "concurrency": 4
}
```

### 4. Bounded Site Crawl
Traverse public, robots-permitted pages on one site. The crawler never crosses to a different host unless `allow_subdomains` is enabled.

- **URL:** `POST /api/v1/crawl`
- **Payload:**
```json
{
  "start_url": "https://example.com/docs",
  "max_pages": 25,
  "max_depth": 2,
  "concurrency": 4,
  "allow_subdomains": false
}
```

### 5. Search Providers
`/api/v1/query` accepts an optional `providers` array, for example `"providers": ["duckduckgo", "brave"]`. Configure the providers through `.env`:

```env
SEARCH_PROVIDERS=duckduckgo,searxng,brave
SEARXNG_URL=https://search.example.com
BRAVE_SEARCH_API_KEY=your-key
```

SearXNG lets an operator select supported upstream engines through their own instance. Brave uses its official API. The service only collects publicly reachable, permitted content; authentication barriers, paywalls, CAPTCHAs, `robots.txt`, and provider/site terms remain respected.

### 6. Health Check
- **URL:** `GET /api/v1/health`
- Verifies both Go server and Python microservice connectivity.

---

## Connecting a JavaScript Frontend Later
The Go gateway has **CORS enabled** (`Access-Control-Allow-Origin: *`). Any frontend built with React, Vue, Svelte, Next.js, or vanilla JS can fetch directly:
```javascript
const response = await fetch('http://localhost:8080/api/v1/query', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: 'Space exploration updates', max_results: 5 })
});
const data = await response.json();
console.log(data.answer, data.sources);
```

## Using the research interface from another application

The repository includes a small independent Go client in
`examples/research-client`. It consumes only the HTTP contract and does not
import crawler, provider, or AI implementation packages:

```go
result, err := researchclient.Ask(
    "http://localhost:8080",
    os.Getenv("RESEARCH_API_KEY"),
    "What are the latest developments in quantum computing?",
)
```

Run its integration test with:

```bash
go test ./examples/research-client
```

## Go SDK

The typed Go SDK covers every public API endpoint:

- `Health`
- `Research`
- `News`
- `Scrape`
- `Crawl`
- `Chat`
- `Crypto`
- `TrendingCrypto`
- `CryptoMarket`
- `FuturesSignals`

Use it from another Go application:

```go
import (
    "context"

    "scrapper/sdk/go/scrapper"
)

client := scrapper.NewClient(
    "http://localhost:8080",
    os.Getenv("RESEARCH_API_KEY"),
)

result, err := client.Research(context.Background(), scrapper.QueryRequest{
    Query:      "What are the latest developments in quantum computing?",
    MaxResults: 5,
})
```

The SDK provides:

- Typed request and response structures
- Context cancellation
- Configurable HTTP clients and timeouts
- API-key and research-scope headers
- Typed `APIError` values for non-2xx responses
- JSON decoding errors that identify the endpoint

Run the SDK tests with:

```bash
go test ./sdk/go/scrapper
```
