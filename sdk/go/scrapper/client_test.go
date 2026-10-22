package scrapper

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestClientSupportsTypedEndpointsAndAuth(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-API-Key") != "client-key" || r.Header.Get("X-API-Scope") != "research" {
			t.Fatal("missing SDK authentication headers")
		}
		var request QueryRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil || request.Query != "test" {
			t.Fatalf("unexpected request: %#v", request)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"query":"test","answer":"Answer [1]","confidence":"high","sources":[{"id":1,"title":"Fixture","url":"https://example.test","summary":"Evidence"}]}`))
	}))
	defer server.Close()

	client := NewClient(server.URL, "client-key")
	result, err := client.Research(context.Background(), QueryRequest{Query: "test"})
	if err != nil {
		t.Fatal(err)
	}
	if result.Answer != "Answer [1]" || result.Sources[0].Summary != "Evidence" {
		t.Fatalf("unexpected response: %#v", result)
	}
}

func TestClientReturnsTypedAPIErrorAndHonorsContext(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"not allowed"}`, http.StatusUnauthorized)
	}))
	defer server.Close()
	client := NewClient(server.URL, "")
	_, err := client.Research(context.Background(), QueryRequest{Query: "test"})
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected typed API error, got %v", err)
	}
	if apiErr.Error() != "scrapper API (401): not allowed" {
		t.Fatalf("unexpected error message: %s", apiErr.Error())
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Nanosecond)
	defer cancel()
	_, err = client.Health(ctx)
	if err == nil {
		t.Fatal("expected context error")
	}
}

func TestClientDefaultURLAndCustomHTTPClient(t *testing.T) {
	defaultClient := NewClient("", "")
	if defaultClient.baseURL != "http://127.0.0.1:8080" {
		t.Fatalf("expected default baseURL http://127.0.0.1:8080, got %s", defaultClient.baseURL)
	}

	customHTTP := &http.Client{Timeout: 5 * time.Second}
	customClient := NewClient("http://custom:9000/", "key").WithHTTPClient(customHTTP)
	if customClient.baseURL != "http://custom:9000" {
		t.Fatalf("expected trimmed baseURL http://custom:9000, got %s", customClient.baseURL)
	}
	if customClient.http != customHTTP {
		t.Fatal("expected custom HTTP client to be configured")
	}
	// nil WithHTTPClient should be a no-op
	customClient.WithHTTPClient(nil)
	if customClient.http != customHTTP {
		t.Fatal("nil client should not overwrite configured http client")
	}
}

func TestClientAllEndpoints(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/api/v1/health":
			_, _ = w.Write([]byte(`{"status":"healthy","service":"go_scraper_gateway","timestamp":"2026-10-22T12:00:00Z"}`))
		case "/api/v1/scrape":
			var req ScrapeRequest
			_ = json.NewDecoder(r.Body).Decode(&req)
			if len(req.URLs) == 0 {
				http.Error(w, `{"error":"missing urls"}`, http.StatusBadRequest)
				return
			}
			_, _ = w.Write([]byte(`{"count":1,"results":[{"url":"https://example.com","status_code":200,"title":"Example"}]}`))
		case "/api/v1/crawl":
			var req CrawlRequest
			_ = json.NewDecoder(r.Body).Decode(&req)
			_, _ = w.Write([]byte(`{"start_url":"https://example.com","count":1,"results":[{"url":"https://example.com","status_code":200}]}`))
		case "/api/v1/news":
			if r.Header.Get("X-API-Key") != "news-key" {
				http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
				return
			}
			_, _ = w.Write([]byte(`{"topic":"tech","count":1,"collected_at":"2026-10-22T12:00:00Z","articles":[{"title":"Tech News","url":"https://news.test"}]}`))
		case "/api/v1/chat":
			var req ChatRequest
			_ = json.NewDecoder(r.Body).Decode(&req)
			_, _ = w.Write([]byte(`{"reply":"Hello!","session_id":"s1","mode":"general","sources":[],"history_length":1}`))
		case "/api/v1/crypto":
			var req CryptoRequest
			_ = json.NewDecoder(r.Body).Decode(&req)
			_, _ = w.Write([]byte(`{"id":"bitcoin","name":"Bitcoin","symbol":"btc","change_24h_pct":2.5,"signal":"neutral","signal_color":"gray","momentum_score":50.0}`))
		case "/api/v1/crypto/trending":
			_, _ = w.Write([]byte(`{"trending":[{"id":"solana","name":"Solana"}]}`))
		case "/api/v1/crypto/market":
			_, _ = w.Write([]byte(`{"count":1,"coins":[{"id":"bitcoin","name":"Bitcoin","symbol":"btc","change_24h_pct":1.2}]}`))
		case "/api/v1/crypto/futures-signals":
			strategy := r.URL.Query().Get("strategy")
			limit := r.URL.Query().Get("limit")
			minVol := r.URL.Query().Get("min_volume")
			if strategy != "short" || limit != "5" || (minVol != "2e+07" && minVol != "20000000") {
				http.Error(w, `{"error":"unexpected query params"}`, http.StatusBadRequest)
				return
			}
			_, _ = w.Write([]byte(`{"count":1,"strategy":"short","signals":[{"symbol":"BTCUSDT","direction":"SHORT","score":75.0}]}`))
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	ctx := context.Background()
	client := NewClient(server.URL, "news-key")

	// 1. Health
	health, err := client.Health(ctx)
	if err != nil || health.Status != "healthy" {
		t.Fatalf("Health failed: %v", err)
	}

	// 2. Scrape
	scrape, err := client.Scrape(ctx, ScrapeRequest{URLs: []string{"https://example.com"}})
	if err != nil || scrape.Count != 1 || scrape.Results[0].Title != "Example" {
		t.Fatalf("Scrape failed: %v", err)
	}

	// 3. Crawl
	crawl, err := client.Crawl(ctx, CrawlRequest{StartURL: "https://example.com", MaxPages: 2})
	if err != nil || crawl.Count != 1 {
		t.Fatalf("Crawl failed: %v", err)
	}

	// 4. News
	news, err := client.News(ctx, NewsRequest{Topic: "tech"})
	if err != nil || news.Count != 1 || news.CollectedAt == "" || news.Articles[0].Title != "Tech News" {
		t.Fatalf("News failed: %v", err)
	}

	// 5. Chat
	chat, err := client.Chat(ctx, ChatRequest{Message: "hello"})
	if err != nil || chat.Reply != "Hello!" {
		t.Fatalf("Chat failed: %v", err)
	}

	// 6. Crypto
	crypto, err := client.Crypto(ctx, CryptoRequest{Coin: "bitcoin"})
	if err != nil || crypto.Symbol != "btc" {
		t.Fatalf("Crypto failed: %v", err)
	}

	// 7. TrendingCrypto
	trending, err := client.TrendingCrypto(ctx)
	if err != nil || len(trending.Trending) != 1 {
		t.Fatalf("TrendingCrypto failed: %v", err)
	}

	// 8. CryptoMarket
	market, err := client.CryptoMarket(ctx, CryptoMarketRequest{Coins: []string{"bitcoin"}})
	if err != nil || market.Count != 1 {
		t.Fatalf("CryptoMarket failed: %v", err)
	}

	// 9. FuturesSignals
	signals, err := client.FuturesSignals(ctx, "short", 5, 20_000_000.0)
	if err != nil || signals.Count != 1 || signals.Signals[0].Symbol != "BTCUSDT" {
		t.Fatalf("FuturesSignals failed: %v", err)
	}
}
