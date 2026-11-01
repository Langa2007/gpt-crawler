package adkagent

import (
	"context"
	"fmt"
	"log"
	"os"
	"strings"
	"sync"
	"time"

	"google.golang.org/genai"

	"google.golang.org/adk/v2/agent"
	"google.golang.org/adk/v2/agent/llmagent"
	"google.golang.org/adk/v2/model"
	"google.golang.org/adk/v2/model/gemini"
	"google.golang.org/adk/v2/model/openaimodel"
	"google.golang.org/adk/v2/runner"
	"google.golang.org/adk/v2/tool"
	"google.golang.org/adk/v2/tool/functiontool"

	"scrapper/internal/crawler"
	"scrapper/internal/service"
)

// ScrapperAgent encapsulates the Google ADK Agent and Runner.
type ScrapperAgent struct {
	mu           sync.RWMutex
	rootAgent    agent.Agent
	runner       *runner.Runner
	engine       *crawler.Engine
	aiClient     *service.AIClient
	modelName    string
	providerName string
	tools        []tool.Tool
}

// AgentRunRequest represents a request to the ADK agent.
type AgentRunRequest struct {
	Prompt    string `json:"prompt"`
	SessionID string `json:"session_id,omitempty"`
}

// AgentRunResponse represents the outcome of an ADK agent execution.
type AgentRunResponse struct {
	Answer     string   `json:"answer"`
	SessionID  string   `json:"session_id"`
	Model      string   `json:"model"`
	Provider   string   `json:"provider"`
	ToolsUsed  []string `json:"tools_used,omitempty"`
	DurationMs int64    `json:"duration_ms"`
}

// NewScrapperAgent initializes an ADK agent with Scrapper tools and an LLM model.
func NewScrapperAgent(engine *crawler.Engine, aiClient *service.AIClient) (*ScrapperAgent, error) {
	ctx := context.Background()
	llm, provName, modelName, err := resolveModel(ctx)
	if err != nil {
		return nil, fmt.Errorf("adk: resolve model: %w", err)
	}

	sa := &ScrapperAgent{
		engine:       engine,
		aiClient:     aiClient,
		modelName:    modelName,
		providerName: provName,
	}

	tools, err := sa.buildTools()
	if err != nil {
		return nil, fmt.Errorf("adk: build tools: %w", err)
	}
	sa.tools = tools

	instruction := "You are Scrapper Agent, an advanced autonomous web research and intelligence bot powered by Google ADK (Agent Development Kit).\n" +
		"You have direct access to tools for live web search, web page scraping, website crawling, crypto market intelligence, futures trading signals, and news.\n" +
		"Guidelines:\n" +
		"1. When asked for factual or current info, use 'web_search' or 'news_feed'.\n" +
		"2. If you need full text or deeper details from a URL, use 'scrape_url'.\n" +
		"3. For cryptocurrency, tokens, or futures trading inquiries, use 'crypto_intel'.\n" +
		"4. To explore a website thoroughly within its boundaries, use 'crawl_site'.\n" +
		"5. Synthesize coherent, accurate, and source-grounded answers citing relevant URLs."

	rootAgent, err := llmagent.New(llmagent.Config{
		Name:        "scrapper_autonomous_agent",
		Model:       llm,
		Description: "Autonomous web intelligence, research, and scraping agent powered by Google ADK.",
		Instruction: instruction,
		Tools:       tools,
	})
	if err != nil {
		return nil, fmt.Errorf("adk: create llm agent: %w", err)
	}
	sa.rootAgent = rootAgent

	r, err := runner.NewInMemory("scrapper_bot", rootAgent)
	if err != nil {
		return nil, fmt.Errorf("adk: create runner: %w", err)
	}
	sa.runner = r

	log.Printf("[ADK] Initialized Scrapper Agent (provider: %s, model: %s, tools: %d)", provName, modelName, len(tools))
	return sa, nil
}

// resolveModel detects Gemini or OpenAI-compatible models from environment variables.
func resolveModel(ctx context.Context) (model.LLM, string, string, error) {
	// 1. Google Gemini (via GEMINI_API_KEY or GOOGLE_API_KEY)
	geminiKey := os.Getenv("GEMINI_API_KEY")
	if geminiKey == "" {
		geminiKey = os.Getenv("GOOGLE_API_KEY")
	}
	if geminiKey != "" {
		modelName := os.Getenv("GEMINI_MODEL")
		if modelName == "" {
			modelName = os.Getenv("DEFAULT_AI_MODEL")
		}
		if modelName == "" || strings.Contains(modelName, "gpt") {
			modelName = "gemini-2.5-flash"
		}
		m, err := gemini.NewModel(ctx, modelName, &genai.ClientConfig{
			APIKey: geminiKey,
		})
		if err == nil {
			return m, "gemini", modelName, nil
		}
		log.Printf("[ADK] Failed to initialize Gemini model: %v. Checking OpenAI fallback...", err)
	}

	// 2. OpenAI / Compatible (ChatGPT, Ollama, Kimi, Qwen, DeepSeek, vLLM)
	openAIKey := os.Getenv("OPENAI_API_KEY")
	baseURL := os.Getenv("OPENAI_BASE_URL")
	if openAIKey == "" {
		openAIKey = os.Getenv("CUSTOM_AI_API_KEY")
	}
	if baseURL == "" {
		baseURL = os.Getenv("CUSTOM_AI_BASE_URL")
	}

	if openAIKey != "" || baseURL != "" {
		modelName := os.Getenv("OPENAI_MODEL")
		if modelName == "" {
			modelName = os.Getenv("CUSTOM_AI_MODEL")
		}
		if modelName == "" {
			modelName = "gpt-4o-mini"
		}
		m, err := openaimodel.NewModel(ctx, modelName, &openaimodel.ClientConfig{
			APIKey:  openAIKey,
			BaseURL: baseURL,
			API:     openaimodel.APIChatCompletions,
		})
		if err == nil {
			return m, "openai_compatible", modelName, nil
		}
		log.Printf("[ADK] Failed to initialize OpenAI model: %v", err)
	}

	return nil, "none", "none", fmt.Errorf("no supported LLM credentials found (set GEMINI_API_KEY or OPENAI_API_KEY/OPENAI_BASE_URL)")
}

// ScrapeURLArgs is the input for the scrape tool.
type ScrapeURLArgs struct {
	URLs []string `json:"urls"`
}

// ScrapeURLResult is the output of the scrape tool.
type ScrapeURLResult struct {
	Count   int                    `json:"count"`
	Results []crawler.ScrapeResult `json:"results"`
}

// CrawlSiteArgs is the input for the crawl tool.
type CrawlSiteArgs struct {
	StartURL string `json:"start_url"`
	MaxPages int    `json:"max_pages,omitempty"`
	MaxDepth int    `json:"max_depth,omitempty"`
}

// WebSearchArgs is the input for web search.
type WebSearchArgs struct {
	Query      string `json:"query"`
	MaxResults int    `json:"max_results,omitempty"`
}

// WebSearchResult is the output of web search.
type WebSearchResult struct {
	Query   string           `json:"query"`
	Count   int              `json:"count"`
	Results []map[string]any `json:"results"`
}

// CryptoIntelArgs is the input for crypto intelligence.
type CryptoIntelArgs struct {
	Coin string `json:"coin,omitempty"`
	Mode string `json:"mode,omitempty"` // "price", "trending", "signals"
}

// NewsFeedArgs is the input for news search.
type NewsFeedArgs struct {
	Topic string `json:"topic"`
	Limit int    `json:"limit,omitempty"`
}

// buildTools sets up all ADK FunctionTools bridging Go & Python scrapers.
func (sa *ScrapperAgent) buildTools() ([]tool.Tool, error) {
	var tools []tool.Tool

	// 1. Web Search Tool
	searchTool, err := functiontool.New(functiontool.Config{
		Name:        "web_search",
		Description: "Search the public web for real-time information, websites, and data sources.",
	}, func(ctx agent.Context, args WebSearchArgs) (WebSearchResult, error) {
		maxRes := args.MaxResults
		if maxRes <= 0 {
			maxRes = 5
		}
		res, err := sa.aiClient.SearchInternet(ctx, args.Query, maxRes, "web", nil)
		if err != nil {
			return WebSearchResult{Query: args.Query, Count: 0}, err
		}
		return WebSearchResult{
			Query:   args.Query,
			Count:   len(res),
			Results: res,
		}, nil
	})
	if err != nil {
		return nil, fmt.Errorf("create web_search tool: %w", err)
	}
	tools = append(tools, searchTool)

	// 2. Scrape URL Tool
	scrapeTool, err := functiontool.New(functiontool.Config{
		Name:        "scrape_url",
		Description: "Scrape content and clean text from one or more web page URLs using high-concurrency Go crawlers.",
	}, func(ctx agent.Context, args ScrapeURLArgs) (ScrapeURLResult, error) {
		if len(args.URLs) == 0 {
			return ScrapeURLResult{}, fmt.Errorf("must supply at least one URL")
		}
		results := sa.engine.ScrapeBatch(ctx, args.URLs, 4)
		for i := range results {
			if results[i].Error == "" && results[i].HTML != "" {
				cleanData, err := sa.aiClient.CleanHTML(ctx, results[i].HTML, results[i].URL)
				if err == nil {
					if text, ok := cleanData["text"].(string); ok && text != "" {
						results[i].CleanText = text
					}
					if title, ok := cleanData["title"].(string); ok && title != "" {
						results[i].Title = title
					}
				}
				results[i].HTML = "" // strip raw HTML to conserve tokens
			}
		}
		return ScrapeURLResult{Count: len(results), Results: results}, nil
	})
	if err != nil {
		return nil, fmt.Errorf("create scrape_url tool: %w", err)
	}
	tools = append(tools, scrapeTool)

	// 3. Crawl Site Tool
	crawlTool, err := functiontool.New(functiontool.Config{
		Name:        "crawl_site",
		Description: "Recursively crawl a website starting from a URL within domain boundaries.",
	}, func(ctx agent.Context, args CrawlSiteArgs) (crawler.CrawlResponse, error) {
		maxPages := args.MaxPages
		if maxPages <= 0 {
			maxPages = 10
		}
		maxDepth := args.MaxDepth
		if maxDepth <= 0 {
			maxDepth = 2
		}
		resp := sa.engine.CrawlSite(ctx, crawler.CrawlRequest{
			StartURL:    args.StartURL,
			MaxPages:    maxPages,
			MaxDepth:    maxDepth,
			Concurrency: 3,
		})
		return resp, nil
	})
	if err != nil {
		return nil, fmt.Errorf("create crawl_site tool: %w", err)
	}
	tools = append(tools, crawlTool)

	// 4. Crypto Intel Tool
	cryptoTool, err := functiontool.New(functiontool.Config{
		Name:        "crypto_intel",
		Description: "Retrieve cryptocurrency spot prices, 24h market momentum, trending tokens, or futures algorithmic trading signals.",
	}, func(ctx agent.Context, args CryptoIntelArgs) (map[string]any, error) {
		mode := strings.ToLower(args.Mode)
		if mode == "trending" {
			return sa.aiClient.GetTrendingCrypto(ctx)
		}
		if mode == "signals" || mode == "futures" {
			sig, err := sa.aiClient.GetFuturesSignals(ctx, "short", 10, 15_000_000)
			if err != nil {
				return nil, err
			}
			return map[string]any{"futures_signals": sig}, nil
		}
		coin := args.Coin
		if coin == "" {
			coin = "bitcoin"
		}
		return sa.aiClient.GetCrypto(ctx, coin)
	})
	if err != nil {
		return nil, fmt.Errorf("create crypto_intel tool: %w", err)
	}
	tools = append(tools, cryptoTool)

	// 5. News Feed Tool
	newsTool, err := functiontool.New(functiontool.Config{
		Name:        "news_feed",
		Description: "Retrieve structured breaking news articles and headlines on any specified topic.",
	}, func(ctx agent.Context, args NewsFeedArgs) (*crawler.NewsResponse, error) {
		limit := args.Limit
		if limit <= 0 {
			limit = 5
		}
		return sa.aiClient.FetchNews(ctx, args.Topic, limit, "w")
	})
	if err != nil {
		return nil, fmt.Errorf("create news_feed tool: %w", err)
	}
	tools = append(tools, newsTool)

	return tools, nil
}

// Run executes the ADK agent on the user's prompt.
func (sa *ScrapperAgent) Run(ctx context.Context, sessionID, prompt string) (*AgentRunResponse, error) {
	start := time.Now()
	if sessionID == "" {
		sessionID = fmt.Sprintf("session-%d", time.Now().UnixNano())
	}

	sa.mu.RLock()
	r := sa.runner
	sa.mu.RUnlock()

	if r == nil {
		return nil, fmt.Errorf("adk runner is not initialized")
	}

	var answerParts []string
	var toolsUsed []string
	toolsSeen := make(map[string]bool)

	userContent := genai.NewContentFromText(prompt, genai.RoleUser)

	for ev, err := range r.Run(ctx, "user", sessionID, userContent, agent.RunConfig{}) {
		if err != nil {
			return nil, fmt.Errorf("adk run event error: %w", err)
		}
		if ev == nil {
			continue
		}

		// Inspect function/tool calls
		if ev.Content != nil {
			for _, part := range ev.Content.Parts {
				if text := part.Text; text != "" {
					answerParts = append(answerParts, text)
				}
				if call := part.FunctionCall; call != nil {
					if !toolsSeen[call.Name] {
						toolsSeen[call.Name] = true
						toolsUsed = append(toolsUsed, call.Name)
					}
				}
			}
		}
	}

	finalAnswer := strings.TrimSpace(strings.Join(answerParts, "\n"))
	if finalAnswer == "" {
		finalAnswer = "Agent completed execution."
	}

	return &AgentRunResponse{
		Answer:     finalAnswer,
		SessionID:  sessionID,
		Model:      sa.modelName,
		Provider:   sa.providerName,
		ToolsUsed:  toolsUsed,
		DurationMs: time.Since(start).Milliseconds(),
	}, nil
}

// Info returns metadata about the active ADK setup.
func (sa *ScrapperAgent) Info() map[string]any {
	sa.mu.RLock()
	defer sa.mu.RUnlock()

	var toolNames []string
	for _, t := range sa.tools {
		toolNames = append(toolNames, t.Name())
	}

	return map[string]any{
		"adk_version":   "v2.6.0",
		"provider":      sa.providerName,
		"model":         sa.modelName,
		"tools":         toolNames,
		"tools_count":   len(toolNames),
		"agent_name":    "scrapper_autonomous_agent",
		"status":        "ready",
	}
}

// Agent returns the underlying root agent.
func (sa *ScrapperAgent) Agent() agent.Agent {
	sa.mu.RLock()
	defer sa.mu.RUnlock()
	return sa.rootAgent
}
