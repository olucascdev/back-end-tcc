package python

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/circuitbreaker"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/retry"
)

// testTimeouts retorna mapa de timeouts padrao para testes.
func testTimeouts() map[string]time.Duration {
	return map[string]time.Duration{
		"chat":             5 * time.Second,
		"summarize":        5 * time.Second,
		"compare":          5 * time.Second,
		"process-document": 5 * time.Second,
		"health":           2 * time.Second,
	}
}

func TestNewClient(t *testing.T) {
	url := "http://localhost:8000"
	timeouts := testTimeouts()

	client := NewClient(url, timeouts, nil)

	if client.BaseURL() != url {
		t.Errorf("expected baseURL %s, got %s", url, client.BaseURL())
	}
	if client.GetTimeout("chat") != 5*time.Second {
		t.Errorf("expected chat timeout 5s, got %s", client.GetTimeout("chat"))
	}
}

func TestClient_ProcessDocument_Success(t *testing.T) {
	// Mock server que simula resposta bem-sucedida do Python
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/process-document" {
			t.Errorf("expected path /process-document, got %s", r.URL.Path)
		}
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Error("expected Content-Type application/json")
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		json.NewEncoder(w).Encode(v1.ProcessDocumentResponse{
			DocumentID:  uuid.MustParse("00000000-0000-0000-0000-000000000001"),
			Status:      "pending",
			ChunksCount: ptrInt(42),
		})
	}))
	defer server.Close()

	client := NewClient(server.URL, testTimeouts(), nil)

	docID := uuid.New()
	req := &v1.ProcessDocumentRequest{
		ProjectID:  uuid.New(),
		DocumentID: docID,
		StorageKey: "s3://bucket/doc.pdf",
		SourceType: "user_upload",
	}

	ctx := context.Background()
	resp, err := client.ProcessDocument(ctx, req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if resp.Status != "pending" {
		t.Errorf("expected status pending, got %s", resp.Status)
	}
	if resp.ChunksCount == nil || *resp.ChunksCount != 42 {
		t.Errorf("expected ChunksCount 42, got %v", resp.ChunksCount)
	}
}

func TestClient_Chat_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat" {
			t.Errorf("expected path /chat, got %s", r.URL.Path)
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{
			Answer:    "Resposta do agente Python.",
			Sources:   []v1.Source{{Document: "doc1.pdf", Page: 3, Score: 0.95}},
			SessionID: "test-session",
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	client := NewClient(server.URL, testTimeouts(), nil)

	req := &v1.ChatRequest{
		ProjectID: uuid.New(),
		SessionID: "test-session",
		Message:   "Ola, mundo",
	}

	ctx := context.Background()
	resp, err := client.Chat(ctx, req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if resp.Answer != "Resposta do agente Python." {
		t.Errorf("expected answer, got %s", resp.Answer)
	}
	if len(resp.Sources) != 1 {
		t.Errorf("expected 1 source, got %d", len(resp.Sources))
	}
	if resp.SessionID != req.SessionID {
		t.Errorf("expected SessionID %s, got %s", req.SessionID, resp.SessionID)
	}
}

func TestClient_Summarize_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/summarize-document" {
			t.Errorf("expected path /summarize-document, got %s", r.URL.Path)
		}

		// Ler request para extrair document_id
		var req v1.SummarizeRequest
		json.NewDecoder(r.Body).Decode(&req)

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.SummarizeResponse{
			DocumentID: req.DocumentID,
			Summary: map[string]string{
				"objective":   "Test objective",
				"methodology": "Test methodology",
				"results":     "Test results",
				"conclusion":  "Test conclusion",
			},
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	client := NewClient(server.URL, testTimeouts(), nil)

	docID := uuid.New()
	req := &v1.SummarizeRequest{
		DocumentID: docID,
		ProjectID:  uuid.New(),
		Format:     "structured",
	}

	ctx := context.Background()
	resp, err := client.Summarize(ctx, req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if resp.DocumentID != docID {
		t.Errorf("expected DocumentID %s, got %s", docID, resp.DocumentID)
	}
	if len(resp.Summary) != 4 {
		t.Errorf("expected 4 summary keys, got %d", len(resp.Summary))
	}
}

func TestClient_Compare_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/compare-documents" {
			t.Errorf("expected path /compare-documents, got %s", r.URL.Path)
		}

		// Ler request para extrair project_id
		var req v1.CompareRequest
		json.NewDecoder(r.Body).Decode(&req)

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.CompareResponse{
			ProjectID:  req.ProjectID,
			Comparison: map[string]string{"theme": "comparison result"},
			Sources:    []v1.Source{},
			CreatedAt:  time.Now().UTC(),
		})
	}))
	defer server.Close()

	client := NewClient(server.URL, testTimeouts(), nil)

	projID := uuid.New()
	req := &v1.CompareRequest{
		ProjectID:   projID,
		DocumentIDs: []uuid.UUID{uuid.New(), uuid.New()},
		Theme:       "metodologia",
	}

	ctx := context.Background()
	resp, err := client.Compare(ctx, req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if resp.ProjectID != projID {
		t.Errorf("expected ProjectID %s, got %s", projID, resp.ProjectID)
	}
	if len(resp.Comparison) == 0 {
		t.Error("expected non-empty Comparison map")
	}
}

func TestClient_ProcessDocument_5xx_Error(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(`{"error":"internal server error"}`))
	}))
	defer server.Close()

	client := NewClient(server.URL, testTimeouts(), nil)

	req := &v1.ProcessDocumentRequest{
		ProjectID:  uuid.New(),
		DocumentID: uuid.New(),
		StorageKey: "s3://bucket/doc.pdf",
		SourceType: "user_upload",
	}

	ctx := context.Background()
	_, err := client.ProcessDocument(ctx, req)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if err != ErrServiceUnavailable {
		t.Errorf("expected ErrServiceUnavailable, got %v", err)
	}
}

func TestClient_Chat_4xx_Error(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte(`{"error":"invalid message"}`))
	}))
	defer server.Close()

	client := NewClient(server.URL, testTimeouts(), nil)

	req := &v1.ChatRequest{
		ProjectID: uuid.New(),
		SessionID: "test-session",
		Message:   "",
	}

	ctx := context.Background()
	_, err := client.Chat(ctx, req)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	// 4xx deve retornar erro de validacao
	if err.Error() == "" {
		t.Error("expected validation error with details")
	}
}

func TestClient_Timeout(t *testing.T) {
	// Server que demora mais que o timeout do client
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(2 * time.Second)
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	// Timeout de 100ms para a operacao process-document
	timeouts := map[string]time.Duration{
		"process-document": 100 * time.Millisecond,
	}
client := NewClient(server.URL, timeouts, nil)

	req := &v1.ProcessDocumentRequest{
		ProjectID:  uuid.New(),
		DocumentID: uuid.New(),
		StorageKey: "s3://bucket/doc.pdf",
		SourceType: "user_upload",
	}

	ctx := context.Background()
	_, err := client.ProcessDocument(ctx, req)
	if err == nil {
		t.Fatal("expected timeout error, got nil")
	}
	if err != ErrTimeout {
		t.Errorf("expected ErrTimeout, got %v", err)
	}
}

func TestClient_ConnectionError(t *testing.T) {
	// URL invalida para simular erro de conexao
	client := NewClient("http://localhost:59999", testTimeouts(), nil)

	req := &v1.ProcessDocumentRequest{
		ProjectID:  uuid.New(),
		DocumentID: uuid.New(),
		StorageKey: "s3://bucket/doc.pdf",
		SourceType: "user_upload",
	}

	ctx := context.Background()
	_, err := client.ProcessDocument(ctx, req)
	if err == nil {
		t.Fatal("expected connection error, got nil")
	}
	if err != ErrServiceUnavailable {
		t.Errorf("expected ErrServiceUnavailable, got %v", err)
	}
}

func TestClient_RequestID_Propagated(t *testing.T) {
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

	client := NewClient(server.URL, testTimeouts(), nil)

	req := &v1.ChatRequest{
		ProjectID: uuid.New(),
		SessionID: "test-session",
		Message:   "hello",
	}

	// Inserir request_id no contexto
	ctx := context.WithValue(context.Background(), "request_id", "test-request-id-123")
	_, err := client.Chat(ctx, req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if receivedRequestID != "test-request-id-123" {
		t.Errorf("expected X-Request-ID test-request-id-123, got %s", receivedRequestID)
	}
}

func TestClient_TimeoutPerOperation(t *testing.T) {
	// Mapa com timeouts diferentes por operacao
	timeouts := map[string]time.Duration{
		"chat":             10 * time.Second,
		"summarize":        20 * time.Second,
		"compare":          15 * time.Second,
		"process-document": 60 * time.Second,
		"health":           3 * time.Second,
	}
	client := NewClient("http://localhost:8000", timeouts, nil)

	// Validar que cada operacao retorna seu timeout especifico
	if client.GetTimeout("chat") != 10*time.Second {
		t.Errorf("expected chat timeout 10s, got %s", client.GetTimeout("chat"))
	}
	if client.GetTimeout("summarize") != 20*time.Second {
		t.Errorf("expected summarize timeout 20s, got %s", client.GetTimeout("summarize"))
	}
	if client.GetTimeout("compare") != 15*time.Second {
		t.Errorf("expected compare timeout 15s, got %s", client.GetTimeout("compare"))
	}
	if client.GetTimeout("process-document") != 60*time.Second {
		t.Errorf("expected process-document timeout 60s, got %s", client.GetTimeout("process-document"))
	}
	if client.GetTimeout("health") != 3*time.Second {
		t.Errorf("expected health timeout 3s, got %s", client.GetTimeout("health"))
	}
}

func TestClient_DefaultTimeoutWhenMissing(t *testing.T) {
	// Mapa vazio — nenhuma operacao configurada
	client := NewClient("http://localhost:8000", map[string]time.Duration{}, nil)

	// Operacao desconhecida deve retornar defaultTimeout (30s)
	if client.GetTimeout("unknown-op") != 30*time.Second {
		t.Errorf("expected default timeout 30s for unknown op, got %s", client.GetTimeout("unknown-op"))
	}

	// Operacao conhecida mas nao no mapa tambem deve retornar default
	if client.GetTimeout("chat") != 30*time.Second {
		t.Errorf("expected default timeout 30s for missing chat, got %s", client.GetTimeout("chat"))
	}
}

func TestClient_Chat_CircuitOpen(t *testing.T) {
	// Criar breaker com threshold baixo para abrir rapidamente
	breakers := circuitbreaker.NewBreakerGroup(circuitbreaker.Config{
		MaxRequests:      1,
		FailureThreshold: 2,
		Timeout:          1 * time.Second,
	})

	// Server que sempre falha (500)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(`{"error":"fail"}`))
	}))
	defer server.Close()

	client := NewClient(server.URL, testTimeouts(), breakers)

	// Disparar falhas consecutivas para abrir o circuito
	for i := 0; i < 2; i++ {
		req := &v1.ChatRequest{
			ProjectID: uuid.New(),
			SessionID: "test-session",
			Message:   "test",
		}
		_, _ = client.Chat(context.Background(), req)
	}

	// Agora o circuito deve estar aberto — chamada nao deve chegar ao server
	callCount := 0
	failingServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{Answer: "ok", Sources: []v1.Source{}, SessionID: "test", CreatedAt: time.Now().UTC()})
	}))
	defer failingServer.Close()

	client2 := NewClient(failingServer.URL, testTimeouts(), breakers)
	req := &v1.ChatRequest{
		ProjectID: uuid.New(),
		SessionID: "test-session",
		Message:   "test",
	}
	_, err := client2.Chat(context.Background(), req)

	if err == nil {
		t.Fatal("expected error when circuit is open, got nil")
	}
	if !errors.Is(err, circuitbreaker.ErrCircuitOpen) {
		t.Errorf("expected ErrCircuitOpen, got %v", err)
	}
	if callCount != 0 {
		t.Errorf("expected no HTTP call when circuit is open, got %d calls", callCount)
	}
}

func ptrInt(i int) *int {
	return &i
}

// testRetryPolicy cria uma politica de retry com delays curtos para testes.
func testRetryPolicy() *retry.Policy {
	return retry.NewPolicy(retry.Config{
		MaxRetries:      3,
		BaseDelay:       5 * time.Millisecond,
		MaxDelay:        20 * time.Millisecond,
		RetryableErrors: []error{ErrServiceUnavailable, ErrTimeout},
	})
}

func TestClient_Chat_RetryOnTimeout(t *testing.T) {
	// Server que falha 2 vezes com 503 (mapeado para ErrServiceUnavailable),
	// depois retorna sucesso na 3a tentativa.
	callCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		if callCount < 3 {
			w.WriteHeader(http.StatusServiceUnavailable)
			w.Write([]byte(`{"error":"unavailable"}`))
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{
			Answer:    "success after retries",
			Sources:   []v1.Source{},
			SessionID: "test-session",
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	client := NewClientWithResilience(server.URL, testTimeouts(), nil, testRetryPolicy())

	req := &v1.ChatRequest{
		ProjectID: uuid.New(),
		SessionID: "test-session",
		Message:   "hello",
	}

	ctx := context.Background()
	resp, err := client.Chat(ctx, req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Answer != "success after retries" {
		t.Errorf("expected 'success after retries', got %s", resp.Answer)
	}
	if callCount != 3 {
		t.Errorf("expected 3 calls (2 failures + 1 success), got %d", callCount)
	}
}

func TestClient_Chat_NoRetryOnValidation(t *testing.T) {
	// Server que retorna 400 (validation error — nao retryable).
	callCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte(`{"error":"invalid input"}`))
	}))
	defer server.Close()

	client := NewClientWithResilience(server.URL, testTimeouts(), nil, testRetryPolicy())

	req := &v1.ChatRequest{
		ProjectID: uuid.New(),
		SessionID: "test-session",
		Message:   "",
	}

	ctx := context.Background()
	_, err := client.Chat(ctx, req)
	if err == nil {
		t.Fatal("expected validation error, got nil")
	}
	// Validation error nao deve ser retentado — apenas 1 chamada
	if callCount != 1 {
		t.Errorf("expected 1 call (no retry for validation), got %d", callCount)
	}
}

func TestClient_ProcessDocument_NoRetry(t *testing.T) {
	// Server que retorna 503 (retryable), mas ProcessDocument NAO aplica retry.
	callCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.WriteHeader(http.StatusServiceUnavailable)
		w.Write([]byte(`{"error":"unavailable"}`))
	}))
	defer server.Close()

	client := NewClientWithResilience(server.URL, testTimeouts(), nil, testRetryPolicy())

	req := &v1.ProcessDocumentRequest{
		ProjectID:  uuid.New(),
		DocumentID: uuid.New(),
		StorageKey: "s3://bucket/doc.pdf",
		SourceType: "user_upload",
	}

	ctx := context.Background()
	_, err := client.ProcessDocument(ctx, req)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if err != ErrServiceUnavailable {
		t.Errorf("expected ErrServiceUnavailable, got %v", err)
	}
	// ProcessDocument nunca aplica retry — apenas 1 chamada
	if callCount != 1 {
		t.Errorf("expected 1 call (no retry for process-document), got %d", callCount)
	}
}
