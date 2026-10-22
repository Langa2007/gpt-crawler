package api

import (
	"net/http"
	"os"
)

func SetupRouter(h *Handler) http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /api/v1/health", h.HealthCheck)
	mux.HandleFunc("POST /api/v1/scrape", h.ScrapeURLs)
	mux.HandleFunc("POST /api/v1/crawl", h.CrawlSite)
	mux.Handle("POST /api/v1/query", researchAuth(http.HandlerFunc(h.QueryInternet)))
	mux.Handle("POST /api/v1/news", researchAuth(http.HandlerFunc(h.GetNews)))

	mux.HandleFunc("POST /api/v1/chat", h.ChatBot)

	mux.HandleFunc("POST /api/v1/crypto", h.GetCrypto)
	mux.HandleFunc("GET /api/v1/crypto/trending", h.GetTrendingCrypto)
	mux.HandleFunc("POST /api/v1/crypto/market", h.GetCryptoMarket)
	mux.HandleFunc("GET /api/v1/crypto/futures-signals", h.GetFuturesSignals)

	// Serve frontend dashboard and widget files.
	frontendDir := os.Getenv("FRONTEND_DIR")
	if frontendDir == "" {
		frontendDir = "frontend"
	}
	widgetDir := os.Getenv("WIDGET_DIR")
	if widgetDir == "" {
		widgetDir = "widget"
	}

	fs := http.FileServer(http.Dir(frontendDir))
	mux.Handle("GET /widget/", http.StripPrefix("/widget", http.FileServer(http.Dir(widgetDir))))
	mux.Handle("/", fs)

	return corsMiddleware(mux)
}

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Session-ID, X-API-Key, X-API-Scope")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}

		next.ServeHTTP(w, r)
	})
}
