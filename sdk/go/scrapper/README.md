# Scrapper Go SDK

Typed Go client for the Scrapper API. It uses the Go standard library and
supports contexts, custom `http.Client` values, and structured API errors.
For clients in other languages, see the [language-neutral OpenAPI contract](../../openapi.yaml).

## Install

```bash
go get github.com/Langa2007/scrapper/sdk/go/scrapper
```

## Quick start

```go
package main

import (
	"context"
	"fmt"
	"log"

	"github.com/Langa2007/scrapper/sdk/go/scrapper"
)

func main() {
	client := scrapper.NewClient("http://localhost:8080", "")

	ctx := context.Background()
	health, err := client.Health(ctx)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("API status:", health.Status)

	result, err := client.Research(ctx, scrapper.QueryRequest{
		Query:      "Recent developments in renewable energy",
		MaxResults: 5,
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(result.Answer)
	for _, source := range result.Sources {
		fmt.Printf("[%d] %s — %s\n", source.ID, source.Title, source.URL)
	}
}
```

The base URL should point to the Go API gateway (port 8080 by default), not the
internal Python service (port 5000). `apiKey` can be empty when research API
authentication is not configured.

## Authentication

When the server has `RESEARCH_API_KEYS` configured, `/api/v1/query` and
`/api/v1/news` require an API key with the `research` scope. The SDK sends
`X-API-Key` and `X-API-Scope: research` when a non-empty key is supplied.

For example, configure the server with:

```bash
export RESEARCH_API_KEYS='replace-with-a-secret:research'
```

Then pass the key to `NewClient`. Other endpoints do not require this key by
default.

## Available methods

All methods accept a `context.Context` and return a typed response and error.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `Health` | `GET /api/v1/health` | Check gateway and Python service health |
| `Research` | `POST /api/v1/query` | Search and synthesize an answer with sources |
| `News` | `POST /api/v1/news` | Fetch articles for a topic |
| `Scrape` | `POST /api/v1/scrape` | Scrape a batch of URLs |
| `Crawl` | `POST /api/v1/crawl` | Crawl a site from a starting URL |
| `Chat` | `POST /api/v1/chat` | Send a chatbot message |
| `Crypto` | `POST /api/v1/crypto` | Get a crypto asset summary |
| `TrendingCrypto` | `GET /api/v1/crypto/trending` | Get trending crypto assets |
| `CryptoMarket` | `POST /api/v1/crypto/market` | Get market data for selected coins |
| `FuturesSignals` | `GET /api/v1/crypto/futures-signals` | Get futures signals |

`NewClient` defaults to `http://127.0.0.1:8080` when the base URL is empty.
Use `WithHTTPClient` to provide a custom HTTP client, for example to set a
different timeout or transport. Non-2xx responses are returned as `*APIError`,
which includes `StatusCode` and `Message` and can be inspected with
`errors.As`.
