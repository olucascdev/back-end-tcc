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
	"github.com/olucasdev/tcc/go-gateway/internal/middleware"
)

// setupProxyTestRouter cria router com middlewares e handlers de proxy
// apontando para o Python mock server fornecido.
func setupProxyTestRouter(pythonURL string) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	client := python.NewClient(pythonURL, 5*time.Second)

	v1Group := r.Group("/api/v1")
	{
		docs := v1Group.Group("/documents")
		{
			docs.POST("/process", ProxyProcessDocument(client))
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
	// Mock Python server
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

	if w.Code != http.StatusAccepted {
		t.Errorf("expected status 202, got %d", w.Code)
	}

	var resp v1.ProcessDocumentResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}
	if resp.Status != "pending" {
		t.Errorf("expected status pending, got %s", resp.Status)
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
	// Mock Python server retornando 500
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

	if w.Code != http.StatusBadGateway {
		t.Errorf("expected status 502, got %d", w.Code)
	}

	var errResp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("failed to parse error response: %v", err)
	}
	if errResp["error"] != "upstream service unavailable" {
		t.Errorf("expected safe error message, got %s", errResp["error"])
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
	// Server que demora mais que o timeout do client (5s no setup)
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

	client := python.NewClient(server.URL, 100*time.Millisecond)

	v1Group := r.Group("/api/v1")
	docs := v1Group.Group("/documents")
	docs.POST("/process", ProxyProcessDocument(client))

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

	if w.Code != http.StatusGatewayTimeout {
		t.Errorf("expected status 504, got %d", w.Code)
	}

	var errResp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("failed to parse error response: %v", err)
	}
	if errResp["error"] != "request timed out while processing" {
		t.Errorf("expected timeout message, got %s", errResp["error"])
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

	client := python.NewClient(server.URL, 100*time.Millisecond)

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
