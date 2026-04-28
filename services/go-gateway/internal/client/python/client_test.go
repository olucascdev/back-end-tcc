package python

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
)

func TestNewClient(t *testing.T) {
	url := "http://localhost:8000"
	timeout := 15 * time.Second

	client := NewClient(url, timeout)

	if client.BaseURL() != url {
		t.Errorf("expected baseURL %s, got %s", url, client.BaseURL())
	}
	if client.Timeout() != timeout {
		t.Errorf("expected timeout %s, got %s", timeout, client.Timeout())
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

	client := NewClient(server.URL, 5*time.Second)

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

	client := NewClient(server.URL, 5*time.Second)

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

	client := NewClient(server.URL, 5*time.Second)

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

	client := NewClient(server.URL, 5*time.Second)

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

	client := NewClient(server.URL, 5*time.Second)

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

	client := NewClient(server.URL, 5*time.Second)

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

	client := NewClient(server.URL, 100*time.Millisecond)

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
	client := NewClient("http://localhost:59999", 1*time.Second)

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

	client := NewClient(server.URL, 5*time.Second)

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

func ptrInt(i int) *int {
	return &i
}
