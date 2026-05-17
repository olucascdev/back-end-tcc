package handlers

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/circuitbreaker"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/queue"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/ratelimit"
	"github.com/olucasdev/tcc/go-gateway/internal/middleware"
)

// setupMockPythonAgent cria um httptest.Server que simula o agente Python
// com handlers para todos os endpoints suportados.
func setupMockPythonAgent() *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		switch r.URL.Path {
		case "/chat":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				return
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(v1.ChatResponse{
				Answer:    "Resposta simulada do agente Python.",
				Sources:   []v1.Source{{Document: "mock-doc.pdf", Page: 1, Score: 0.95}},
				SessionID: "integration-session",
				CreatedAt: time.Now().UTC(),
			})

		case "/summarize-document":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				return
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(v1.SummarizeResponse{
				DocumentID: uuid.MustParse("00000000-0000-0000-0000-000000000001"),
				Summary: map[string]string{
					"objective":   "Objetivo simulado.",
					"methodology": "Metodologia simulada.",
					"results":     "Resultados simulados.",
					"conclusion":  "Conclusao simulada.",
				},
				CreatedAt: time.Now().UTC(),
			})

		case "/compare-documents":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				return
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(v1.CompareResponse{
				ProjectID: uuid.MustParse("00000000-0000-0000-0000-000000000001"),
				Comparison: map[string]string{
					"theme_a": "Comparacao no tema A.",
					"theme_b": "Comparacao no tema B.",
				},
				Sources:   []v1.Source{{Document: "doc1.pdf", Page: 1, Score: 0.9}},
				CreatedAt: time.Now().UTC(),
			})

		case "/process-document":
			if r.Method != http.MethodPost {
				w.WriteHeader(http.StatusMethodNotAllowed)
				return
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(v1.ProcessDocumentResponse{
				DocumentID:  uuid.MustParse("00000000-0000-0000-0000-000000000001"),
				Status:      "ready",
				ChunksCount: func() *int { i := 42; return &i }(),
			})

		case "/health":
			if r.Method != http.MethodGet {
				w.WriteHeader(http.StatusMethodNotAllowed)
				return
			}
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(map[string]string{"status": "ok"})

		default:
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"error": "not found"})
		}
	}))
}

// setupGatewayRouter cria um router Gin com rotas v1 registradas,
// apontando para o servidor Python fornecido via client real.
func setupGatewayRouter(pythonURL string) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	client := python.NewClient(pythonURL, map[string]time.Duration{
		"chat":             5 * time.Second,
		"summarize":        5 * time.Second,
		"compare":          5 * time.Second,
		"process-document": 5 * time.Second,
		"health":           2 * time.Second,
		"research-gaps":    5 * time.Second,
	}, nil)

	q := queue.NewMemoryQueue(100)

	v1Group := r.Group("/api/v1")
	{
		docs := v1Group.Group("/documents")
		{
			docs.POST("/process", ProxyProcessDocument(client, q))
			docs.POST("/summarize", ProxySummarize(client))
			docs.POST("/compare", ProxyCompare(client))
			docs.POST("/research/gaps", ProxyResearchGaps(client))
		}
		chat := v1Group.Group("/chat")
		{
			chat.POST("", ProxyChat(client, nil))
		}
	}
	return r
}

// TestIntegration_ChatProxy_Flow testa o fluxo completo de chat:
// requisicao HTTP -> gateway -> mock Python -> resposta com answer e sources.
func TestIntegration_ChatProxy_Flow(t *testing.T) {
	server := setupMockPythonAgent()
	defer server.Close()

	r := setupGatewayRouter(server.URL)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "integration-session",
		"message": "Qual a metodologia usada no documento?"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d; body: %s", w.Code, w.Body.String())
	}

	var resp v1.ChatResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}

	if resp.Answer != "Resposta simulada do agente Python." {
		t.Errorf("expected answer 'Resposta simulada do agente Python.', got %q", resp.Answer)
	}

	if len(resp.Sources) != 1 {
		t.Fatalf("expected 1 source, got %d", len(resp.Sources))
	}

	if resp.Sources[0].Document != "mock-doc.pdf" {
		t.Errorf("expected source document 'mock-doc.pdf', got %q", resp.Sources[0].Document)
	}

	if resp.SessionID != "integration-session" {
		t.Errorf("expected session_id 'integration-session', got %q", resp.SessionID)
	}
}

// TestIntegration_SummarizeProxy_Flow testa o fluxo completo de resumo:
// requisicao HTTP -> gateway -> mock Python -> resposta com summary.
func TestIntegration_SummarizeProxy_Flow(t *testing.T) {
	server := setupMockPythonAgent()
	defer server.Close()

	r := setupGatewayRouter(server.URL)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"document_id": "00000000-0000-0000-0000-000000000001",
		"format": "structured"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/documents/summarize", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d; body: %s", w.Code, w.Body.String())
	}

	var resp v1.SummarizeResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}

	if _, ok := resp.Summary["objective"]; !ok {
		t.Error("expected 'objective' key in summary")
	}

	if _, ok := resp.Summary["methodology"]; !ok {
		t.Error("expected 'methodology' key in summary")
	}
}

// TestIntegration_RateLimit_BlocksAfterBurst testa que o rate limiter
// bloqueia requisicoes apos exceder o burst configurado.
// Envia 30 requests rapidos e verifica que alguns recebem 429.
func TestIntegration_RateLimit_BlocksAfterBurst(t *testing.T) {
	server := setupMockPythonAgent()
	defer server.Close()

	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	// Rate limiter agressivo: 2 req/s com burst de 5 para teste rapido
	limiter := ratelimit.New(2, 5)
	r.Use(limiter.Middleware())

	client := python.NewClient(server.URL, map[string]time.Duration{
		"chat": 5 * time.Second,
	}, nil)

	v1Group := r.Group("/api/v1")
	chat := v1Group.Group("/chat")
	chat.POST("", ProxyChat(client, nil))

	var blockedCount int
	var successCount int

	// Enviar 30 requests rapidos com mesma chave (mesmo IP)
	for i := 0; i < 30; i++ {
		body := bytes.NewReader([]byte(`{
			"project_id": "00000000-0000-0000-0000-000000000001",
			"session_id": "ratelimit-session",
			"message": "Teste de rate limit"
		}`))

		req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)

		if w.Code == http.StatusTooManyRequests {
			blockedCount++
		} else if w.Code == http.StatusOK {
			successCount++
		}
	}

	// Com burst=5 e rate=2, espera-se que alguns requests sejam bloqueados
	if blockedCount == 0 {
		t.Error("expected some requests to be blocked with 429, but none were")
	}

	if successCount == 0 {
		t.Error("expected some requests to succeed, but none did")
	}

	t.Logf("rate limit test: %d succeeded, %d blocked out of 30 requests", successCount, blockedCount)
}

// TestIntegration_CircuitBreaker_OpensAfterFailures testa que o circuit breaker
// abre apos falhas consecutivas e retorna 503 sem chamar o upstream.
// Mock retorna 500, envia 6 requests, verifica que ultimos recebem 503.
func TestIntegration_CircuitBreaker_OpensAfterFailures(t *testing.T) {
	// Breaker com threshold baixo: abre apos 2 falhas consecutivas
	breakers := circuitbreaker.NewBreakerGroup(circuitbreaker.Config{
		MaxRequests:      1,
		FailureThreshold: 2,
		Timeout:          5 * time.Second,
	})

	// Contador de chamadas ao mock para verificar que breaker corta trafego
	var callCount atomic.Int64

	// Server que sempre retorna 500
	failingServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount.Add(1)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": "internal failure"})
	}))
	defer failingServer.Close()

	client := python.NewClient(failingServer.URL, map[string]time.Duration{
		"chat": 5 * time.Second,
	}, breakers)

	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	v1Group := r.Group("/api/v1")
	chat := v1Group.Group("/chat")
	chat.POST("", ProxyChat(client, nil))

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "cb-session",
		"message": "Teste circuit breaker"
	}`)

	// Enviar 6 requests consecutivos
	var lastStatus int
	for i := 0; i < 6; i++ {
		req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
		lastStatus = w.Code

		t.Logf("request %d: status=%d", i+1, w.Code)
	}

	// As ultimas requisicoes devem receber 503 (circuit breaker aberto)
	if lastStatus != http.StatusServiceUnavailable {
		t.Errorf("expected last request to get 503 (circuit breaker open), got %d", lastStatus)
	}

	// Verificar que o mock nao foi chamado 6 vezes (breaker cortou trafego)
	calls := callCount.Load()
	if calls >= 6 {
		t.Errorf("expected circuit breaker to reduce upstream calls, but got %d calls (should be < 6)", calls)
	}

	t.Logf("circuit breaker test: upstream called %d times out of 6 requests", calls)
}
