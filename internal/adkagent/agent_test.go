package adkagent

import (
	"context"
	"testing"

	"scrapper/internal/crawler"
	"scrapper/internal/service"
)

func TestScrapperAgentToolsBuilding(t *testing.T) {
	engine := crawler.NewEngine()
	aiClient := service.NewAIClient("http://127.0.0.1:5000")

	sa := &ScrapperAgent{
		engine:       engine,
		aiClient:     aiClient,
		modelName:    "test-model",
		providerName: "mock",
	}

	tools, err := sa.buildTools()
	if err != nil {
		t.Fatalf("buildTools failed: %v", err)
	}

	if len(tools) != 5 {
		t.Fatalf("expected 5 tools, got %d", len(tools))
	}

	expectedTools := map[string]bool{
		"web_search":   false,
		"scrape_url":   false,
		"crawl_site":   false,
		"crypto_intel": false,
		"news_feed":    false,
	}

	for _, tl := range tools {
		name := tl.Name()
		if _, exists := expectedTools[name]; exists {
			expectedTools[name] = true
		} else {
			t.Errorf("unexpected tool name: %s", name)
		}
	}

	for name, found := range expectedTools {
		if !found {
			t.Errorf("expected tool %s was not found", name)
		}
	}
}

func TestScrapperAgentInfo(t *testing.T) {
	sa := &ScrapperAgent{
		modelName:    "gemini-2.5-flash",
		providerName: "gemini",
	}

	info := sa.Info()
	if info["provider"] != "gemini" {
		t.Errorf("expected provider gemini, got %v", info["provider"])
	}
	if info["model"] != "gemini-2.5-flash" {
		t.Errorf("expected model gemini-2.5-flash, got %v", info["model"])
	}
	if info["adk_version"] != "v2.6.0" {
		t.Errorf("expected adk_version v2.6.0, got %v", info["adk_version"])
	}
}

func TestResolveModelWithoutCredentials(t *testing.T) {
	t.Setenv("GEMINI_API_KEY", "")
	t.Setenv("GOOGLE_API_KEY", "")
	t.Setenv("OPENAI_API_KEY", "")
	t.Setenv("OPENAI_BASE_URL", "")
	t.Setenv("CUSTOM_AI_API_KEY", "")
	t.Setenv("CUSTOM_AI_BASE_URL", "")

	_, _, _, err := resolveModel(context.Background())
	if err == nil {
		t.Fatal("expected error when no credentials provided, got nil")
	}
}

