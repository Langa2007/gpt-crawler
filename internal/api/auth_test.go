package api

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestResearchAuthRequiresScopedKeyWhenConfigured(t *testing.T) {
	t.Setenv("RESEARCH_API_KEYS", "client-key:research")
	handler := researchAuth(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))

	for _, test := range []struct {
		name   string
		key    string
		scope  string
		status int
	}{
		{"missing", "", "", http.StatusUnauthorized},
		{"wrong key", "other", "research", http.StatusUnauthorized},
		{"wrong scope", "client-key", "admin", http.StatusUnauthorized},
		{"valid", "client-key", "research", http.StatusNoContent},
	} {
		t.Run(test.name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodPost, "/api/v1/query", nil)
			request.Header.Set("X-API-Key", test.key)
			request.Header.Set("X-API-Scope", test.scope)
			recorder := httptest.NewRecorder()
			handler.ServeHTTP(recorder, request)
			if recorder.Code != test.status {
				t.Fatalf("got status %d, want %d", recorder.Code, test.status)
			}
		})
	}
}
