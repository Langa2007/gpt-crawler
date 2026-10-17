package researchclient

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
)

type Request struct {
	Query      string   `json:"query"`
	MaxResults int      `json:"max_results,omitempty"`
	Providers  []string `json:"providers,omitempty"`
}

type Source struct {
	ID      int    `json:"id"`
	Title   string `json:"title"`
	URL     string `json:"url"`
	Summary string `json:"summary"`
}

type Response struct {
	Query      string   `json:"query"`
	Answer     string   `json:"answer"`
	Sources    []Source `json:"sources"`
	Confidence string   `json:"confidence"`
	Errors     []string `json:"errors,omitempty"`
}

func Ask(baseURL, apiKey, query string) (Response, error) {
	payload, err := json.Marshal(Request{Query: query, MaxResults: 5})
	if err != nil {
		return Response{}, err
	}
	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(baseURL, "/")+"/api/v1/query", strings.NewReader(string(payload)))
	if err != nil {
		return Response{}, err
	}
	req.Header.Set("Content-Type", "application/json")
	if apiKey != "" {
		req.Header.Set("X-API-Key", apiKey)
		req.Header.Set("X-API-Scope", "research")
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return Response{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return Response{}, fmt.Errorf("research API returned %s", resp.Status)
	}
	var result Response
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return Response{}, err
	}
	return result, nil
}
