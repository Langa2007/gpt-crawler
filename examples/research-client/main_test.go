package researchclient

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSecondApplicationUsesResearchContract(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-API-Key") != "client-key" || r.Header.Get("X-API-Scope") != "research" {
			t.Fatalf("research credentials were not sent")
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"query":"test","answer":"Answer [1]","confidence":"high","sources":[{"id":1,"title":"Fixture","url":"https://example.test","summary":"Evidence","provider":"fixture"}]}`))
	}))
	defer server.Close()

	result, err := Ask(server.URL, "client-key", "test")
	if err != nil {
		t.Fatal(err)
	}
	if result.Answer != "Answer [1]" || len(result.Sources) != 1 || result.Sources[0].Summary != "Evidence" {
		t.Fatalf("unexpected research response: %#v", result)
	}
}
