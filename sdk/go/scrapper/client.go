// Package scrapper provides a typed client for the Scrapper HTTP API.
package scrapper

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type Client struct {
	baseURL string
	apiKey  string
	http    *http.Client
}

func NewClient(baseURL, apiKey string) *Client {
	if strings.TrimSpace(baseURL) == "" {
		baseURL = "http://127.0.0.1:8080"
	}
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		apiKey:  apiKey,
		http:    &http.Client{Timeout: 60 * time.Second},
	}
}

func (c *Client) WithHTTPClient(client *http.Client) *Client {
	if client != nil {
		c.http = client
	}
	return c
}

type APIError struct {
	StatusCode int
	Message    string
}

func (e *APIError) Error() string {
	return fmt.Sprintf("scrapper API (%d): %s", e.StatusCode, e.Message)
}

type HealthResponse struct {
	Status        string         `json:"status"`
	Service       string         `json:"service"`
	Timestamp     string         `json:"timestamp"`
	PythonService string         `json:"python_service"`
	PythonInfo    map[string]any `json:"python_info"`
}

type Source struct {
	ID          int    `json:"id"`
	Title       string `json:"title"`
	URL         string `json:"url"`
	Summary     string `json:"summary,omitempty"`
	Provider    string `json:"provider,omitempty"`
	CollectedAt string `json:"collected_at,omitempty"`
}

type QueryRequest struct {
	Query      string   `json:"query"`
	MaxResults int      `json:"max_results,omitempty"`
	Providers  []string `json:"providers,omitempty"`
}

type QueryResponse struct {
	Query      string   `json:"query"`
	Answer     string   `json:"answer"`
	Sources    []Source `json:"sources"`
	Confidence string   `json:"confidence"`
	DurationMs int64    `json:"duration_ms"`
	Providers  []string `json:"providers,omitempty"`
	Errors     []string `json:"errors,omitempty"`
}

type ScrapeRequest struct {
	URLs        []string `json:"urls"`
	Concurrency int      `json:"concurrency,omitempty"`
	TimeoutSec  int      `json:"timeout_sec,omitempty"`
}

type ScrapeResult struct {
	URL         string            `json:"url"`
	FinalURL    string            `json:"final_url,omitempty"`
	StatusCode  int               `json:"status_code"`
	Title       string            `json:"title"`
	CleanText   string            `json:"clean_text"`
	Description string            `json:"description,omitempty"`
	ContentType string            `json:"content_type,omitempty"`
	Links       []string          `json:"links,omitempty"`
	Metadata    map[string]string `json:"metadata,omitempty"`
	DurationMs  int64             `json:"duration_ms"`
	Error       string            `json:"error,omitempty"`
}

type ScrapeResponse struct {
	Count   int            `json:"count"`
	Results []ScrapeResult `json:"results"`
}

type CrawlRequest struct {
	StartURL        string `json:"start_url"`
	MaxPages        int    `json:"max_pages,omitempty"`
	MaxDepth        int    `json:"max_depth,omitempty"`
	Concurrency     int    `json:"concurrency,omitempty"`
	AllowSubdomains bool   `json:"allow_subdomains,omitempty"`
}

type CrawlResponse struct {
	StartURL string         `json:"start_url"`
	Count    int            `json:"count"`
	Results  []ScrapeResult `json:"results"`
}

type NewsRequest struct {
	Topic     string `json:"topic"`
	Limit     int    `json:"limit,omitempty"`
	Timeframe string `json:"timeframe,omitempty"`
}

type NewsArticle struct {
	Title         string `json:"title"`
	URL           string `json:"url"`
	Summary       string `json:"summary"`
	Author        string `json:"author,omitempty"`
	PublishedDate string `json:"published_date,omitempty"`
	Source        string `json:"source"`
	Image         string `json:"image,omitempty"`
}

type NewsResponse struct {
	Topic    string        `json:"topic"`
	Count    int           `json:"count"`
	Articles []NewsArticle `json:"articles"`
}

type ChatRequest struct {
	Message     string `json:"message"`
	SessionID   string `json:"session_id,omitempty"`
	Mode        string `json:"mode,omitempty"`
	SiteContext string `json:"site_context,omitempty"`
}

type ChatResponse struct {
	Reply         string           `json:"reply"`
	SessionID     string           `json:"session_id"`
	Mode          string           `json:"mode"`
	Sources       []map[string]any `json:"sources"`
	HistoryLength int              `json:"history_length"`
}

type CryptoRequest struct {
	Coin string `json:"coin"`
}

type CryptoAsset struct {
	ID            string         `json:"id"`
	Name          string         `json:"name"`
	Symbol        string         `json:"symbol"`
	Image         string         `json:"image,omitempty"`
	PriceUSD      *float64       `json:"price_usd"`
	Change1hPct   *float64       `json:"change_1h_pct,omitempty"`
	Change24hPct  float64        `json:"change_24h_pct"`
	Change7dPct   *float64       `json:"change_7d_pct,omitempty"`
	MarketCapUSD  *float64       `json:"market_cap_usd,omitempty"`
	Volume24hUSD  *float64       `json:"volume_24h_usd,omitempty"`
	High24hUSD    *float64       `json:"high_24h_usd,omitempty"`
	Low24hUSD     *float64       `json:"low_24h_usd,omitempty"`
	Signal        string         `json:"signal"`
	SignalColor   string         `json:"signal_color"`
	MomentumScore float64        `json:"momentum_score"`
	LastUpdated   string         `json:"last_updated,omitempty"`
	Disclaimer    string         `json:"disclaimer,omitempty"`
	Collection    map[string]any `json:"collection,omitempty"`
}

type CryptoMarketRequest struct {
	Coins []string `json:"coins,omitempty"`
	Limit int      `json:"limit,omitempty"`
}

type CryptoMarketResponse struct {
	Count      int            `json:"count"`
	Coins      []CryptoAsset  `json:"coins"`
	Collection map[string]any `json:"collection,omitempty"`
}

type TrendingResponse struct {
	Trending   []map[string]any `json:"trending"`
	Collection map[string]any   `json:"collection,omitempty"`
}

type FuturesSignalsResponse struct {
	Count      int             `json:"count"`
	Strategy   string          `json:"strategy"`
	Signals    []FuturesSignal `json:"signals"`
	Collection map[string]any  `json:"collection,omitempty"`
}

type FuturesSignal struct {
	Symbol            string  `json:"symbol"`
	Base              string  `json:"base"`
	Direction         string  `json:"direction"`
	Price             float64 `json:"price"`
	ChangePct         float64 `json:"change_pct"`
	VolumeUSDT        float64 `json:"volume_usdt"`
	High24h           float64 `json:"high_24h"`
	Low24h            float64 `json:"low_24h"`
	PositionInRange   float64 `json:"position_in_range"`
	Score             float64 `json:"score"`
	ConfirmationScore float64 `json:"confirmation_score"`
	ConfidencePct     float64 `json:"confidence_pct"`
	SignalStatus      string  `json:"signal_status"`
	EntryLive         bool    `json:"entry_live"`
	RiskWarning       string  `json:"risk_warning"`
	Entry             float64 `json:"entry"`
	SL                float64 `json:"sl"`
	TP1               float64 `json:"tp1"`
	TP2               float64 `json:"tp2"`
	TP3               float64 `json:"tp3"`
	Leverage          int     `json:"leverage"`
	RR                float64 `json:"rr"`
	RiskPct           float64 `json:"risk_pct"`
}

func (c *Client) do(ctx context.Context, method, path string, request, response any) error {
	var body io.Reader
	if request != nil {
		data, err := json.Marshal(request)
		if err != nil {
			return fmt.Errorf("encode request: %w", err)
		}
		body = bytes.NewReader(data)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, body)
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	if request != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if c.apiKey != "" {
		req.Header.Set("X-API-Key", c.apiKey)
		req.Header.Set("X-API-Scope", "research")
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("request %s %s: %w", method, path, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		var payload struct {
			Error string `json:"error"`
		}
		_ = json.NewDecoder(resp.Body).Decode(&payload)
		if payload.Error == "" {
			payload.Error = resp.Status
		}
		return &APIError{StatusCode: resp.StatusCode, Message: payload.Error}
	}
	if response == nil {
		return nil
	}
	if err := json.NewDecoder(resp.Body).Decode(response); err != nil {
		return fmt.Errorf("decode %s response: %w", path, err)
	}
	return nil
}

func (c *Client) Health(ctx context.Context) (HealthResponse, error) {
	var result HealthResponse
	return result, c.do(ctx, http.MethodGet, "/api/v1/health", nil, &result)
}

func (c *Client) Research(ctx context.Context, request QueryRequest) (QueryResponse, error) {
	var result QueryResponse
	return result, c.do(ctx, http.MethodPost, "/api/v1/query", request, &result)
}

func (c *Client) News(ctx context.Context, request NewsRequest) (NewsResponse, error) {
	var result NewsResponse
	return result, c.do(ctx, http.MethodPost, "/api/v1/news", request, &result)
}

func (c *Client) Scrape(ctx context.Context, request ScrapeRequest) (ScrapeResponse, error) {
	var result ScrapeResponse
	return result, c.do(ctx, http.MethodPost, "/api/v1/scrape", request, &result)
}

func (c *Client) Crawl(ctx context.Context, request CrawlRequest) (CrawlResponse, error) {
	var result CrawlResponse
	return result, c.do(ctx, http.MethodPost, "/api/v1/crawl", request, &result)
}

func (c *Client) Chat(ctx context.Context, request ChatRequest) (ChatResponse, error) {
	var result ChatResponse
	return result, c.do(ctx, http.MethodPost, "/api/v1/chat", request, &result)
}

func (c *Client) Crypto(ctx context.Context, request CryptoRequest) (CryptoAsset, error) {
	var result CryptoAsset
	return result, c.do(ctx, http.MethodPost, "/api/v1/crypto", request, &result)
}

func (c *Client) TrendingCrypto(ctx context.Context) (TrendingResponse, error) {
	var result TrendingResponse
	return result, c.do(ctx, http.MethodGet, "/api/v1/crypto/trending", nil, &result)
}

func (c *Client) CryptoMarket(ctx context.Context, request CryptoMarketRequest) (CryptoMarketResponse, error) {
	var result CryptoMarketResponse
	return result, c.do(ctx, http.MethodPost, "/api/v1/crypto/market", request, &result)
}

func (c *Client) FuturesSignals(ctx context.Context, strategy string, limit int, minVolume float64) (FuturesSignalsResponse, error) {
	query := url.Values{}
	query.Set("strategy", strategy)
	query.Set("limit", fmt.Sprintf("%d", limit))
	query.Set("min_volume", fmt.Sprintf("%g", minVolume))
	path := "/api/v1/crypto/futures-signals?" + query.Encode()
	var result FuturesSignalsResponse
	return result, c.do(ctx, http.MethodGet, path, nil, &result)
}
