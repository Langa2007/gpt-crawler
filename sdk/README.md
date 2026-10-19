# Scrapper SDKs and API contract

Scrapper exposes a language-neutral HTTP API described by
[openapi.yaml](openapi.yaml). Use the OpenAPI document as the source contract
for any language: import it into an OpenAPI client generator or call the REST
endpoints directly with that language's HTTP library.

The Go SDK in [`go/scrapper`](go/scrapper/README.md) is the first maintained
typed client. Clients generated from the OpenAPI document can target other
languages without changing the Scrapper server.

The API gateway defaults to `http://localhost:8080`. Port 5000 is the internal
Python service and is not the SDK base URL. The `query` and `news` operations
accept optional research credentials when the server has not configured
`RESEARCH_API_KEYS`; when configured, send `X-API-Key` and
`X-API-Scope: research`.

## Direct HTTP example

The API uses JSON and standard HTTP verbs, so any language with an HTTP client
can use it. For example, the same request can be issued with curl:

```bash
curl http://localhost:8080/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"Recent developments in renewable energy","max_results":5}'
```

See the OpenAPI document for all paths, request fields, response types, and
error responses.
