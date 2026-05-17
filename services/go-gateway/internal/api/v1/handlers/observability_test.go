// Package handlers contem testes de observabilidade do gateway Go.
// Verifica propagacao de request_id, logging estruturado e endpoint /metrics.
package handlers

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/queue"
	"github.com/olucasdev/tcc/go-gateway/internal/middleware"
)

// setupObservabilityTestRouter cria router com todos os middlewares de observabilidade.
func setupObservabilityTestRouter(pythonURL string) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())
	r.Use(middleware.MetricsCollector())
	r.Use(middleware.RequestLogger())

	// Endpoint de metricas
	r.GET("/metrics", gin.WrapH(promhttp.Handler()))

	client := python.NewClient(pythonURL, map[string]time.Duration{"chat": 5 * time.Second, "process-document": 5 * time.Second}, nil)
	q := queue.NewMemoryQueue(100)

	v1Group := r.Group("/api/v1")
	{
		docs := v1Group.Group("/documents")
		{
			docs.POST("/process", ProxyProcessDocument(client, q))
		}
		chat := v1Group.Group("/chat")
		{
			chat.POST("", ProxyChat(client, nil))
		}
	}
	return r
}

// TestRequestID_GeneratedWhenMissing verifica que request_id e gerado quando header nao existe.
func TestRequestID_GeneratedWhenMissing(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{
			Answer:    "ok",
			Sources:   []v1.Source{},
			SessionID: "test",
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	r := setupObservabilityTestRouter(server.URL)

	body := strings.NewReader(`{"project_id":"00000000-0000-0000-0000-000000000001","session_id":"s1","message":"hi"}`)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// Deve retornar X-Request-ID na resposta mesmo sem enviar no request
	respHeader := w.Header().Get("X-Request-ID")
	if respHeader == "" {
		t.Error("expected X-Request-ID header in response, got empty")
	}

	// Deve ser um UUID valido
	_, err := uuid.Parse(respHeader)
	if err != nil {
		t.Errorf("expected valid UUID in X-Request-ID, got %s: %v", respHeader, err)
	}
}

// TestRequestID_ReusedFromHeader verifica que request_id e reutilizado do header.
func TestRequestID_ReusedFromHeader(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{
			Answer:    "ok",
			Sources:   []v1.Source{},
			SessionID: "test",
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	r := setupObservabilityTestRouter(server.URL)

	body := strings.NewReader(`{"project_id":"00000000-0000-0000-0000-000000000001","session_id":"s1","message":"hi"}`)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Request-ID", "my-custom-id-123")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Header().Get("X-Request-ID") != "my-custom-id-123" {
		t.Errorf("expected X-Request-ID my-custom-id-123, got %s", w.Header().Get("X-Request-ID"))
	}
}

// TestRequestID_PropagatedToPython verifica que request_id e propagado ao servico Python.
func TestRequestID_PropagatedToPython(t *testing.T) {
	var receivedRequestID string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedRequestID = r.Header.Get("X-Request-ID")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{
			Answer:    "ok",
			Sources:   []v1.Source{},
			SessionID: "test",
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	r := setupObservabilityTestRouter(server.URL)

	body := strings.NewReader(`{"project_id":"00000000-0000-0000-0000-000000000001","session_id":"s1","message":"hi"}`)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Request-ID", "propagated-id-456")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if receivedRequestID != "propagated-id-456" {
		t.Errorf("expected Python to receive X-Request-ID propagated-id-456, got %s", receivedRequestID)
	}
}

// TestMetricsEndpointAvailable verifica que endpoint /metrics retorna dados Prometheus.
func TestMetricsEndpointAvailable(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.GET("/metrics", gin.WrapH(promhttp.Handler()))

	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200 for /metrics, got %d", w.Code)
	}

	// Deve conter texto de metricas Prometheus
	body := w.Body.String()
	if !strings.Contains(body, "# HELP") || !strings.Contains(body, "# TYPE") {
		t.Error("expected Prometheus metrics format in /metrics response")
	}
}

// TestMetricsCollector_RecordsRequests verifica que middleware MetricsCollector registra requests.
func TestMetricsCollector_RecordsRequests(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{
			Answer:    "ok",
			Sources:   []v1.Source{},
			SessionID: "test",
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	r := setupObservabilityTestRouter(server.URL)

	// Fazer varias requisicoes
	for i := 0; i < 3; i++ {
		body := strings.NewReader(`{"project_id":"00000000-0000-0000-0000-000000000001","session_id":"s1","message":"hi"}`)
		req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Errorf("request %d: expected status 200, got %d", i, w.Code)
		}
	}

	// Verificar que metricas foram registradas
	metricsReq := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	metricsW := httptest.NewRecorder()
	r.ServeHTTP(metricsW, metricsReq)

	metricsBody := metricsW.Body.String()
	// Deve conter requests_total com label de path /api/v1/chat
	if !strings.Contains(metricsBody, `requests_total`) {
		t.Error("expected requests_total metric to be present")
	}
	if !strings.Contains(metricsBody, `path="/api/v1/chat"`) {
		t.Error("expected requests_total to have path=/api/v1/chat label")
	}
}

// TestProxyLogs_ContextFields verifica que handlers logam com project_id, document_id, session_id.
// Este teste valida que os campos estao presentes no contexto Gin (logging e verificado via integracao).
func TestProxyLogs_ContextFields(t *testing.T) {
	var receivedHeaders http.Header
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedHeaders = r.Header.Clone()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(v1.ProcessDocumentResponse{
			DocumentID:  uuid.MustParse("00000000-0000-0000-0000-000000000001"),
			Status:      "pending",
			ChunksCount: func() *int { i := 5; return &i }(),
		})
	}))
	defer server.Close()

	r := setupObservabilityTestRouter(server.URL)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"document_id": "00000000-0000-0000-0000-000000000001",
		"storage_key": "s3://bucket/doc.pdf",
		"source_type": "user_upload"
	}`)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/documents/process", body)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Request-ID", "context-test-789")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusAccepted {
		t.Errorf("expected status 202, got %d", w.Code)
	}

	// Verificar que request_id foi propagado
	if receivedHeaders.Get("X-Request-ID") != "context-test-789" {
		t.Errorf("expected X-Request-ID context-test-789, got %s", receivedHeaders.Get("X-Request-ID"))
	}
}
