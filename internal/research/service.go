package research

import (
	"context"
	"fmt"

	"scrapper/internal/crawler"
)

type Retriever interface {
	Retrieve(ctx context.Context, query string, limit int, providers []string) ([]map[string]any, error)
}

type Scraper interface {
	ScrapeBatch(ctx context.Context, urls []string, concurrency int) []crawler.ScrapeResult
}

type Answerer interface {
	Answer(ctx context.Context, query string, documents []crawler.ScrapeResult) (Answer, error)
}

type Answer struct {
	Text       string
	Confidence string
	Sources    []crawler.SourceSummary
	Errors     []string
}

type Service struct {
	retriever Retriever
	scraper   Scraper
	answerer  Answerer
}

func NewService(retriever Retriever, scraper Scraper, answerer Answerer) *Service {
	return &Service{retriever: retriever, scraper: scraper, answerer: answerer}
}

func (s *Service) Research(ctx context.Context, query string, limit int, providers []string) (Answer, error) {
	results, err := s.retriever.Retrieve(ctx, query, limit, providers)
	if err != nil {
		return Answer{}, fmt.Errorf("retrieve research sources: %w", err)
	}
	if len(results) == 0 {
		return Answer{Text: "No search results found for the given query.", Confidence: "none"}, nil
	}

	urls := make([]string, 0, len(results))
	for _, result := range results {
		if url, ok := result["url"].(string); ok && url != "" {
			urls = append(urls, url)
		}
	}
	scraped := s.scraper.ScrapeBatch(ctx, urls, 5)
	documents := make([]crawler.ScrapeResult, 0, len(scraped))
	for index, document := range scraped {
		if document.Error == "" && document.CleanText != "" {
			if index < len(results) {
				document.Metadata = map[string]string{
					"provider":     stringValue(results[index]["provider"]),
					"collected_at": stringValue(results[index]["collected_at"]),
				}
			}
			documents = append(documents, document)
			continue
		}
		if index >= len(results) {
			continue
		}
		snippet, _ := results[index]["snippet"].(string)
		title, _ := results[index]["title"].(string)
		documents = append(documents, crawler.ScrapeResult{
			URL: urls[index], Title: title, CleanText: snippet,
			Metadata: map[string]string{
				"provider":     stringValue(results[index]["provider"]),
				"collected_at": stringValue(results[index]["collected_at"]),
			},
		})
	}

	if len(documents) == 0 {
		return Answer{Text: "No relevant web pages could be collected for this query.", Confidence: "low"}, nil
	}
	return s.answerer.Answer(ctx, query, documents)
}

func stringValue(value any) string {
	result, _ := value.(string)
	return result
}
