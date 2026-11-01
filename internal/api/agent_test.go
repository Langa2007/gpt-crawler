package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"scrapper/internal/crawler"
	"scrapper/internal/service"
)

func TestAgentEndpointsWhenUnconfigured(t *testing.T) {
	t.Setenv("GEMINI_API_KEY", "")
	t.Setenv("GOOGLE_API_KEY", "")
	t.Setenv("OPENAI_API_KEY", "")
	t.Setenv("OPENAI_BASE_URL", "")

	engine := crawler.NewEngine()
	aiClient := service.NewAIClient("http://127.0.0.1:5000")
	handler := NewHandler(engine, aiClient)
	router := SetupRouter(handler)

	// 1. GET /api/v1/agent/info
	reqInfo := httptest.NewRequest(http.MethodGet, "/api/v1/agent/info", nil)
	rrInfo := httptest.NewRecorder()
	router.ServeHTTP(rrInfo, reqInfo)

	if rrInfo.Code != http.StatusOK {
		t.Fatalf("expected 200 from agent/info, got %d", rrInfo.Code)
	}

	var infoRes map[string]any
	if err := json.NewDecoder(rrInfo.Body).Decode(&infoRes); err != nil {
		t.Fatalf("failed to decode agent/info response: %v", err)
	}
	if infoRes["status"] != "unconfigured" {
		t.Errorf("expected status 'unconfigured', got %v", infoRes["status"])
	}

	// 2. POST /api/v1/agent/run when unconfigured
	reqRun := httptest.NewRequest(http.MethodPost, "/api/v1/agent/run", strings.NewReader(`{"prompt":"hello"}`))
	rrRun := httptest.NewRecorder()
	router.ServeHTTP(rrRun, reqRun)

	if rrRun.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 from agent/run when unconfigured, got %d", rrRun.Code)
	}

	// 3. GET /api/v1/health should include adk_agent
	reqHealth := httptest.NewRequest(http.MethodGet, "/api/v1/health", nil)
	rrHealth := httptest.NewRecorder()
	router.ServeHTTP(rrHealth, reqHealth)

	if rrHealth.Code != http.StatusOK {
		t.Fatalf("expected 200 from health, got %d", rrHealth.Code)
	}

	var healthRes map[string]any
	if err := json.NewDecoder(rrHealth.Body).Decode(&healthRes); err != nil {
		t.Fatalf("failed to decode health response: %v", err)
	}
	if _, exists := healthRes["adk_agent"]; !exists {
		t.Errorf("expected 'adk_agent' field in health response")
	}
}

