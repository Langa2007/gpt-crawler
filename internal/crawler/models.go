package crawler

type ScrapeJob struct {
	URL        string            `json:"url"`
	TimeoutSec int               `json:"timeout_sec,omitempty"`
	Headers    map[string]string `json:"headers,omitempty"`
}

type ScrapeResult struct {
	URL         string            `json:"url"`
	FinalURL    string            `json:"final_url,omitempty"`
	StatusCode  int               `json:"status_code"`
	Title       string            `json:"title"`
	HTML        string            `json:"html,omitempty"`
	CleanText   string            `json:"clean_text"`
	Description string            `json:"description,omitempty"`
	ContentType string            `json:"content_type,omitempty"`
	Links       []string          `json:"links,omitempty"`
	Metadata    map[string]string `json:"metadata,omitempty"`
	DurationMs  int64             `json:"duration_ms"`
	Error       string            `json:"error,omitempty"`
}

type ScrapeBatchRequest struct {
	URLs        []string `json:"urls"`
	Concurrency int      `json:"concurrency,omitempty"`
	TimeoutSec  int      `json:"timeout_sec,omitempty"`
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

type SearchAndQueryRequest struct {
	Query      string   `json:"query"`
	MaxResults int      `json:"max_results,omitempty"`
	Providers  []string `json:"providers,omitempty"`
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
	Topic       string        `json:"topic"`
	Count       int           `json:"count"`
	CollectedAt string        `json:"collected_at,omitempty"`
	Errors      []string      `json:"errors,omitempty"`
	Articles    []NewsArticle `json:"articles"`
}

type QueryResponse struct {
	Query      string          `json:"query"`
	Answer     string          `json:"answer"`
	Sources    []SourceSummary `json:"sources"`
	Confidence string          `json:"confidence"`
	DurationMs int64           `json:"duration_ms"`
	Providers  []string        `json:"providers,omitempty"`
	Errors     []string        `json:"errors,omitempty"`
}

type SourceSummary struct {
	ID          int    `json:"id"`
	Title       string `json:"title"`
	URL         string `json:"url"`
	Summary     string `json:"summary,omitempty"`
	Provider    string `json:"provider,omitempty"`
	CollectedAt string `json:"collected_at,omitempty"`
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

type CryptoMarketRequest struct {
	Coins []string `json:"coins,omitempty"`
	Limit int      `json:"limit,omitempty"`
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

type FuturesSignalsResponse struct {
	Count      int             `json:"count"`
	Strategy   string          `json:"strategy"`
	Signals    []FuturesSignal `json:"signals"`
	Collection map[string]any  `json:"collection,omitempty"`
}
