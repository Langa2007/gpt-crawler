package api

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	"scrapper/internal/adkagent"
	"scrapper/internal/crawler"
	"scrapper/internal/research"
	"scrapper/internal/service"
)

type Handler struct {
	engine   *crawler.Engine
	aiClient *service.AIClient
	research *research.Service
	agent    *adkagent.ScrapperAgent
}

func NewHandler(engine *crawler.Engine, aiClient *service.AIClient) *Handler {
	agent, err := adkagent.NewScrapperAgent(engine, aiClient)
	if err != nil {
		log.Printf("[ADK] Agent not active (%v) - falling back to microservice mode", err)
	}
	return &Handler{
		engine:   engine,
		aiClient: aiClient,
		research: research.NewService(aiClient, engine, aiClient),
		agent:    agent,
	}
}

func (h *Handler) HealthCheck(w http.ResponseWriter, r *http.Request) {
	pyHealth, err := h.aiClient.Health(r.Context())
	pyStatus := "connected"
	if err != nil {
		pyStatus = "unreachable: " + err.Error()
	}

	var adkStatus map[string]any
	if h.agent != nil {
		adkStatus = h.agent.Info()
	} else {
		adkStatus = map[string]any{
			"status": "unconfigured",
			"note":   "Set GEMINI_API_KEY or OPENAI_API_KEY to activate Google ADK agent",
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"status":         "healthy",
		"service":        "go_scraper_gateway",
		"timestamp":      time.Now().UTC().Format(time.RFC3339),
		"python_service": pyStatus,
		"python_info":    pyHealth,
		"adk_agent":      adkStatus,
	})
}

func (h *Handler) ScrapeURLs(w http.ResponseWriter, r *http.Request) {
	var req crawler.ScrapeBatchRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request payload: "+err.Error())
		return
	}

	if len(req.URLs) == 0 {
		writeError(w, http.StatusBadRequest, "must provide at least one URL in 'urls'")
		return
	}

	concurrency := req.Concurrency
	if concurrency <= 0 {
		concurrency = 5
	}

	ctx := r.Context()
	if req.TimeoutSec > 0 {
		timeout := time.Duration(req.TimeoutSec) * time.Second
		if timeout > 60*time.Second {
			timeout = 60 * time.Second
		}
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, timeout)
		defer cancel()
	}
	results := h.engine.ScrapeBatch(ctx, req.URLs, concurrency)

	for i := range results {
		if results[i].Error == "" && results[i].HTML != "" {
			cleanData, err := h.aiClient.CleanHTML(r.Context(), results[i].HTML, results[i].URL)
			if err == nil {
				if cleanText, ok := cleanData["text"].(string); ok && len(cleanText) > 0 {
					results[i].CleanText = cleanText
				}
				if title, ok := cleanData["title"].(string); ok && title != "" {
					results[i].Title = title
				}
			}
			results[i].HTML = ""
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"count":   len(results),
		"results": results,
	})
}

func (h *Handler) CrawlSite(w http.ResponseWriter, r *http.Request) {
	var req crawler.CrawlRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request payload: "+err.Error())
		return
	}
	if req.StartURL == "" {
		writeError(w, http.StatusBadRequest, "start_url cannot be empty")
		return
	}
	writeJSON(w, http.StatusOK, h.engine.CrawlSite(r.Context(), req))
}

func (h *Handler) QueryInternet(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	var req crawler.SearchAndQueryRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request payload: "+err.Error())
		return
	}

	if req.Query == "" {
		writeError(w, http.StatusBadRequest, "query cannot be empty")
		return
	}

	maxResults := req.MaxResults
	if maxResults <= 0 {
		maxResults = 5
	}
	if maxResults > 10 {
		maxResults = 10
	}

	answer, err := h.research.Research(r.Context(), req.Query, maxResults, req.Providers)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "research failed: "+err.Error())
		return
	}

	writeJSON(w, http.StatusOK, crawler.QueryResponse{
		Query:      req.Query,
		Answer:     answer.Text,
		Sources:    answer.Sources,
		Confidence: answer.Confidence,
		DurationMs: time.Since(start).Milliseconds(),
		Providers:  req.Providers,
		Errors:     answer.Errors,
	})
}

func (h *Handler) GetNews(w http.ResponseWriter, r *http.Request) {
	var req crawler.NewsRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request payload: "+err.Error())
		return
	}

	if req.Topic == "" {
		writeError(w, http.StatusBadRequest, "topic cannot be empty")
		return
	}

	limit := req.Limit
	if limit <= 0 {
		limit = 10
	}
	if limit > 25 {
		limit = 25
	}

	timeframe := req.Timeframe
	if timeframe == "" {
		timeframe = "w"
	}

	newsRes, err := h.aiClient.FetchNews(r.Context(), req.Topic, limit, timeframe)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to fetch news: "+err.Error())
		return
	}

	writeJSON(w, http.StatusOK, newsRes)
}

func (h *Handler) ChatBot(w http.ResponseWriter, r *http.Request) {
	var req crawler.ChatRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request payload: "+err.Error())
		return
	}
	if req.Message == "" {
		writeError(w, http.StatusBadRequest, "message cannot be empty")
		return
	}
	if req.SessionID == "" {
		req.SessionID = "default"
	}
	if req.Mode == "" {
		req.Mode = "general"
	}

	if h.agent != nil {
		prompt := req.Message
		if req.Mode != "general" {
			prompt = fmt.Sprintf("Conversation mode: %s\n\n%s", req.Mode, prompt)
		}
		if strings.TrimSpace(req.SiteContext) != "" {
			prompt = fmt.Sprintf("Website context:\n%s\n\nUser request:\n%s", req.SiteContext, prompt)
		}

		agentResponse, err := h.agent.Run(r.Context(), req.SessionID, prompt)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "ADK chatbot error: "+err.Error())
			return
		}
		writeJSON(w, http.StatusOK, crawler.ChatResponse{
			Reply:         agentResponse.Answer,
			SessionID:     agentResponse.SessionID,
			Mode:          req.Mode,
			Sources:       []map[string]any{},
			HistoryLength: 0,
		})
		return
	}

	resp, err := h.aiClient.Chat(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "chatbot error: "+err.Error())
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) GetCrypto(w http.ResponseWriter, r *http.Request) {
	var req crawler.CryptoRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request payload: "+err.Error())
		return
	}
	if req.Coin == "" {
		writeError(w, http.StatusBadRequest, "coin cannot be empty")
		return
	}

	data, err := h.aiClient.GetCrypto(r.Context(), req.Coin)
	if err != nil {
		if data == nil {
			writeError(w, http.StatusNotFound, err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, data)
}

func (h *Handler) GetTrendingCrypto(w http.ResponseWriter, r *http.Request) {
	data, err := h.aiClient.GetTrendingCrypto(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "trending crypto error: "+err.Error())
		return
	}
	writeJSON(w, http.StatusOK, data)
}

func (h *Handler) GetCryptoMarket(w http.ResponseWriter, r *http.Request) {
	var req crawler.CryptoMarketRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request payload: "+err.Error())
		return
	}
	limit := req.Limit
	if limit <= 0 {
		limit = 10
	}
	data, err := h.aiClient.GetCryptoMarket(r.Context(), req.Coins, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "market error: "+err.Error())
		return
	}
	writeJSON(w, http.StatusOK, data)
}

func (h *Handler) GetFuturesSignals(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	strategy := q.Get("strategy")
	if strategy == "" {
		strategy = "short"
	}

	limit := 10
	if ls := q.Get("limit"); ls != "" {
		if n, err := strconv.Atoi(ls); err == nil && n > 0 {
			limit = n
		}
	}

	minVolume := 15_000_000.0
	if mv := q.Get("min_volume"); mv != "" {
		if v, err := strconv.ParseFloat(mv, 64); err == nil && v > 0 {
			minVolume = v
		}
	}

	data, err := h.aiClient.GetFuturesSignals(r.Context(), strategy, limit, minVolume)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "futures signals error: "+err.Error())
		return
	}
	writeJSON(w, http.StatusOK, data)
}

func (h *Handler) RunAgent(w http.ResponseWriter, r *http.Request) {
	if h.agent == nil {
		writeError(w, http.StatusServiceUnavailable, "Google ADK agent is not configured with an LLM model. Configure GEMINI_API_KEY or OPENAI_API_KEY in .env.")
		return
	}

	var req adkagent.AgentRunRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request payload: "+err.Error())
		return
	}

	if strings.TrimSpace(req.Prompt) == "" {
		writeError(w, http.StatusBadRequest, "prompt cannot be empty")
		return
	}

	resp, err := h.agent.Run(r.Context(), req.SessionID, req.Prompt)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "adk agent execution failed: "+err.Error())
		return
	}

	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) AgentInfo(w http.ResponseWriter, r *http.Request) {
	if h.agent == nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"status": "unconfigured",
			"adk":    "google.golang.org/adk/v2",
			"note":   "Set GEMINI_API_KEY or OPENAI_API_KEY to activate ADK autonomous agent",
		})
		return
	}
	writeJSON(w, http.StatusOK, h.agent.Info())
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]any{
		"error":  message,
		"status": status,
	})
}
