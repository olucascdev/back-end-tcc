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

	"github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/circuitbreaker"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/queue"
	"github.com/olucasdev/tcc/go-gateway/internal/middleware"
)

// setupProxyTestRouter cria router com middlewares e handlers de proxy
// apontando para o Python mock server fornecido.
func setupProxyTestRouter(pythonURL string) *gin.Engine {
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
	}, nil)

	// Fila em memoria para testes de processamento de documento
	q := queue.NewMemoryQueue(100)

	v1Group := r.Group("/api/v1")
	{
		docs := v1Group.Group("/documents")
		{
			docs.POST("/process", ProxyProcessDocument(client, q))
			docs.POST("/summarize", ProxySummarize(client))
			docs.POST("/compare", ProxyCompare(client))
		}
		chat := v1Group.Group("/chat")
		{
			chat.POST("", ProxyChat(client))
		}
	}
	return r
}

func TestProxyProcessDocument_Success(t *testing.T) {
	// Mock Python server (nao sera chamado diretamente, apenas para router setup)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(v1.ProcessDocumentResponse{
			DocumentID:  uuid.MustParse("00000000-0000-0000-0000-000000000001"),
			Status:      "pending",
			ChunksCount: func() *int { i := 10; return &i }(),
		})
	}))
	defer server.Close()

	r := setupProxyTestRouter(server.URL)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"document_id": "00000000-0000-0000-0000-000000000001",
		"storage_key": "s3://bucket/doc.pdf",
		"source_type": "user_upload"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/documents/process", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// Agora retorna 202 com job_id para consulta assincrona
	if w.Code != http.StatusAccepted {
		t.Errorf("expected status 202, got %d", w.Code)
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}
	if _, ok := resp["job_id"]; !ok {
		t.Errorf("expected job_id in response")
	}
	if status, ok := resp["status"].(string); !ok || status != "pending" {
		t.Errorf("expected status pending, got %v", resp["status"])
	}
}

func TestProxyChat_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{
			Answer:    "Resposta do agente.",
			Sources:   []v1.Source{{Document: "doc.pdf", Page: 1, Score: 0.9}},
			SessionID: "sess-1",
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	r := setupProxyTestRouter(server.URL)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "sess-1",
		"message": "Ola"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	var resp v1.ChatResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}
	if resp.Answer != "Resposta do agente." {
		t.Errorf("expected answer, got %s", resp.Answer)
	}
}

func TestProxyProcessDocument_Upstream502(t *testing.T) {
	// Com fila assincrona, o handler sempre retorna 202 ao enfileirar.
	// Erros do upstream sao tratados pelo worker pool, nao pelo handler.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(`{"error":"internal error"}`))
	}))
	defer server.Close()

	r := setupProxyTestRouter(server.URL)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"document_id": "00000000-0000-0000-0000-000000000001",
		"storage_key": "s3://bucket/doc.pdf",
		"source_type": "user_upload"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/documents/process", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// Handler assincrono retorna 202 mesmo com upstream falho
	if w.Code != http.StatusAccepted {
		t.Errorf("expected status 202, got %d", w.Code)
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}
	if _, ok := resp["job_id"]; !ok {
		t.Errorf("expected job_id in response")
	}
}

func TestProxyChat_Upstream502(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		w.Write([]byte(`{"error":"bad gateway"}`))
	}))
	defer server.Close()

	r := setupProxyTestRouter(server.URL)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "sess-1",
		"message": "Ola"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadGateway {
		t.Errorf("expected status 502, got %d", w.Code)
	}
}

func TestProxyProcessDocument_Timeout504(t *testing.T) {
	// Com fila assincrona, o handler retorna 202 ao enfileirar.
	// Timeouts sao tratados pelo worker pool durante processamento.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(10 * time.Second)
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	// Criar client com timeout curto para teste
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	client := python.NewClient(server.URL, map[string]time.Duration{
		"process-document": 100 * time.Millisecond,
	}, nil)

	// Fila em memoria para teste
	q := queue.NewMemoryQueue(100)

	v1Group := r.Group("/api/v1")
	docs := v1Group.Group("/documents")
	docs.POST("/process", ProxyProcessDocument(client, q))

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"document_id": "00000000-0000-0000-0000-000000000001",
		"storage_key": "s3://bucket/doc.pdf",
		"source_type": "user_upload"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/documents/process", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// Handler assincrono retorna 202 ao enfileirar job
	if w.Code != http.StatusAccepted {
		t.Errorf("expected status 202, got %d", w.Code)
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}
	if _, ok := resp["job_id"]; !ok {
		t.Errorf("expected job_id in response")
	}
}

func TestProxyChat_Timeout504(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(10 * time.Second)
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	client := python.NewClient(server.URL, map[string]time.Duration{
		"process-document": 100 * time.Millisecond,
	}, nil)

	v1Group := r.Group("/api/v1")
	chat := v1Group.Group("/chat")
	chat.POST("", ProxyChat(client))

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "sess-1",
		"message": "Ola"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusGatewayTimeout {
		t.Errorf("expected status 504, got %d", w.Code)
	}
}

func TestProxyProcessDocument_InvalidBody(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	r := setupProxyTestRouter(server.URL)

	// Body JSON invalido
	body := strings.NewReader(`{invalid json}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/documents/process", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected status 400, got %d", w.Code)
	}
}

func TestProxy_RequestID_Propagated(t *testing.T) {
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

	r := setupProxyTestRouter(server.URL)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "sess-1",
		"message": "Ola"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Request-ID", "custom-req-id-123")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// Verificar que X-Request-ID foi propagado na resposta
	if w.Header().Get("X-Request-ID") != "custom-req-id-123" {
		t.Errorf("expected X-Request-ID custom-req-id-123, got %s", w.Header().Get("X-Request-ID"))
	}
}

func TestProxyChat_CircuitBreaker503(t *testing.T) {
	// Criar breaker com threshold baixo para abrir rapidamente
	breakers := circuitbreaker.NewBreakerGroup(circuitbreaker.Config{
		MaxRequests:      1,
		FailureThreshold: 2,
		Timeout:          1 * time.Second,
	})

	// Server que sempre falha (500) para abrir o circuito
	failingServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(`{"error":"fail"}`))
	}))
	defer failingServer.Close()

	client := python.NewClient(failingServer.URL, map[string]time.Duration{
		"chat": 5 * time.Second,
	}, breakers)

	// Disparar falhas consecutivas para abrir o circuito
	for i := 0; i < 2; i++ {
		req := &v1.ChatRequest{
			ProjectID: uuid.New(),
			SessionID: "sess-1",
			Message:   "test",
		}
		_, _ = client.Chat(nil, req)
	}

	// Agora criar router com client que tem circuito aberto
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	v1Group := r.Group("/api/v1")
	chat := v1Group.Group("/chat")
	chat.POST("", ProxyChat(client))

	// Requisicao deve retornar 503 sem chegar ao server
	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "sess-1",
		"message": "Ola"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected status 503, got %d", w.Code)
	}

	var errResp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("failed to parse error response: %v", err)
	}
	expectedMsg := "upstream service temporarily unavailable due to circuit breaker"
	if errResp["error"] != expectedMsg {
		t.Errorf("expected error message %q, got %q", expectedMsg, errResp["error"])
	}
}

func TestProxyProcessDocument_QueueFull_503(t *testing.T) {
	// Criar fila com capacidade 1 para testar fila cheia
	q := queue.NewMemoryQueue(1)

	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	client := python.NewClient("http://localhost:9999", map[string]time.Duration{
		"process-document": 5 * time.Second,
	}, nil)

	v1Group := r.Group("/api/v1")
	docs := v1Group.Group("/documents")
	docs.POST("/process", ProxyProcessDocument(client, q))

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"document_id": "00000000-0000-0000-0000-000000000001",
		"storage_key": "s3://bucket/doc.pdf",
		"source_type": "user_upload"
	}`)

	// Primeiro request deve ser aceito (fila vazia)
	req1 := httptest.NewRequest(http.MethodPost, "/api/v1/documents/process", body)
	req1.Header.Set("Content-Type", "application/json")
	w1 := httptest.NewRecorder()
	r.ServeHTTP(w1, req1)

	if w1.Code != http.StatusAccepted {
		t.Errorf("expected first request status 202, got %d", w1.Code)
	}

	// Consumir o job da fila para liberar espaco no canal, mas manter no mapa
	job, ok := q.Dequeue()
	if !ok {
		t.Fatal("expected to dequeue first job")
	}

	// Segundo request deve ser aceito (canal tem espaco agora)
	req2 := httptest.NewRequest(http.MethodPost, "/api/v1/documents/process", body)
	req2.Header.Set("Content-Type", "application/json")
	w2 := httptest.NewRecorder()
	r.ServeHTTP(w2, req2)

	if w2.Code != http.StatusAccepted {
		t.Errorf("expected second request status 202, got %d", w2.Code)
	}

	// Terceiro request deve falhar com 503 (fila cheia)
	req3 := httptest.NewRequest(http.MethodPost, "/api/v1/documents/process", body)
	req3.Header.Set("Content-Type", "application/json")
	w3 := httptest.NewRecorder()
	r.ServeHTTP(w3, req3)

	if w3.Code != http.StatusServiceUnavailable {
		t.Errorf("expected status 503 when queue full, got %d", w3.Code)
	}

	var errResp map[string]string
	if err := json.Unmarshal(w3.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("failed to parse error response: %v", err)
	}
	if !strings.Contains(errResp["error"], "queue is full") {
		t.Errorf("expected queue full error message, got %s", errResp["error"])
	}

	// Verificar que todos os 3 jobs foram registrados no mapa
	_, ok = q.GetJob(job.ID)
	if !ok {
		t.Error("expected first job to be in map")
	}
}

func TestGetJobStatus_Found(t *testing.T) {
	q := queue.NewMemoryQueue(100)

	// Inserir job manualmente para teste
	job := &queue.Job{
		ID:         "test-job-123",
		DocumentID: uuid.New(),
		ProjectID:  uuid.New(),
		StorageKey: "s3://bucket/doc.pdf",
		Status:     queue.StatusPending,
		CreatedAt:  time.Now().UTC(),
		UpdatedAt:  time.Now().UTC(),
	}
	q.Enqueue(job)

	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	v1Group := r.Group("/api/v1")
	docs := v1Group.Group("/documents")
	docs.GET("/jobs/:job_id", GetJobStatus(q))

	req := httptest.NewRequest(http.MethodGet, "/api/v1/documents/jobs/test-job-123", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}
	if resp["job_id"] != "test-job-123" {
		t.Errorf("expected job_id test-job-123, got %v", resp["job_id"])
	}
	if resp["status"] != "pending" {
		t.Errorf("expected status pending, got %v", resp["status"])
	}
}

func TestGetJobStatus_NotFound(t *testing.T) {
	q := queue.NewMemoryQueue(100)

	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	v1Group := r.Group("/api/v1")
	docs := v1Group.Group("/documents")
	docs.GET("/jobs/:job_id", GetJobStatus(q))

	req := httptest.NewRequest(http.MethodGet, "/api/v1/documents/jobs/nonexistent-job", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected status 404, got %d", w.Code)
	}

	var errResp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("failed to parse error response: %v", err)
	}
	if errResp["error"] != "job not found" {
		t.Errorf("expected 'job not found' error, got %s", errResp["error"])
	}
}
