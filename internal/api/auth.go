package api

import (
	"crypto/subtle"
	"net/http"
	"os"
	"strings"
)

type apiCredential struct {
	key    string
	scopes map[string]bool
}

func researchAuth(next http.Handler) http.Handler {
	credentials := loadCredentials(os.Getenv("RESEARCH_API_KEYS"))
	if len(credentials) == 0 {
		return next
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		provided := r.Header.Get("X-API-Key")
		scope := r.Header.Get("X-API-Scope")
		for _, credential := range credentials {
			if subtle.ConstantTimeCompare([]byte(provided), []byte(credential.key)) == 1 &&
				credential.scopes[scope] {
				next.ServeHTTP(w, r)
				return
			}
		}
		writeError(w, http.StatusUnauthorized, "valid research API key and scope are required")
	})
}

func loadCredentials(raw string) []apiCredential {
	var credentials []apiCredential
	for _, item := range strings.Split(raw, ",") {
		parts := strings.SplitN(strings.TrimSpace(item), ":", 2)
		if parts[0] == "" {
			continue
		}
		scopes := map[string]bool{"research": true}
		if len(parts) == 2 {
			scopes = map[string]bool{}
			for _, scope := range strings.Split(parts[1], "|") {
				scopes[strings.TrimSpace(scope)] = true
			}
		}
		credentials = append(credentials, apiCredential{key: parts[0], scopes: scopes})
	}
	return credentials
}
