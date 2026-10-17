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

	ctx, cancel := context.WithTimeout(context.Background(), time.Nanosecond)
	defer cancel()
	_, err = client.Health(ctx)
	if err == nil {
		t.Fatal("expected context error")
	}
}
