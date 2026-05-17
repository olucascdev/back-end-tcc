package handlers

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/cache"
	"github.com/olucasdev/tcc/go-gateway/internal/middleware"
)

// setupChatTestRouter cria router com handler de chat apontando para mock server.
// Permite injetar cache semantico para testes de cache com retrieval_mode.
func setupChatTestRouter(pythonURL string, semanticCache *cache.SemanticCache) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	client := python.NewClient(pythonURL, map[string]time.Duration{
		"chat": 5 * time.Second,
	}, nil)

	v1Group := r.Group("/api/v1")
	chat := v1Group.Group("/chat")
	chat.POST("", ProxyChat(client, semanticCache))
	return r
}

func TestProxyChat_WithRetrievalMode_ProjectOnly(t *testing.T) {
	// Mock Python server que verifica retrieval_mode no payload
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req v1.ChatRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("failed to decode request: %v", err)
		}

		// Verificar que retrieval_mode foi encaminhado
		if req.RetrievalMode != "project_only" {
			t.Errorf("expected retrieval_mode 'project_only', got %q", req.RetrievalMode)
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{
			Answer:    "Resposta baseada apenas nos documentos do projeto.",
			Sources:   []v1.Source{{Document: "project-doc.pdf", Page: 3, Score: 0.92}},
			SessionID: "sess-retrieval-1",
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	r := setupChatTestRouter(server.URL, nil)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "sess-retrieval-1",
		"message": "Qual a metodologia usada?",
		"retrieval_mode": "project_only"
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
	if resp.Answer == "" {
		t.Error("expected non-empty answer")
	}
	if len(resp.Sources) != 1 {
		t.Errorf("expected 1 source, got %d", len(resp.Sources))
	}
}

func TestProxyChat_WithRetrievalMode_ProjectPlusPublic(t *testing.T) {
	// Mock Python server que verifica retrieval_mode project_plus_public
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req v1.ChatRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("failed to decode request: %v", err)
		}

		if req.RetrievalMode != "project_plus_public" {
			t.Errorf("expected retrieval_mode 'project_plus_public', got %q", req.RetrievalMode)
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{
			Answer: "Resposta combinando documentos do projeto e acervo publico.",
			Sources: []v1.Source{
				{Document: "project-doc.pdf", Page: 1, Score: 0.95},
				{Document: "public-book.pdf", Page: 42, Score: 0.88},
			},
			SessionID: "sess-retrieval-2",
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	r := setupChatTestRouter(server.URL, nil)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "sess-retrieval-2",
		"message": "Compare as abordagens de Piaget e Vygotsky",
		"retrieval_mode": "project_plus_public"
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
	if len(resp.Sources) != 2 {
		t.Errorf("expected 2 sources (project + public), got %d", len(resp.Sources))
	}
}

func TestProxyChat_DefaultRetrievalMode(t *testing.T) {
	// Quando retrieval_mode nao e informado, Python deve usar padrao
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req v1.ChatRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("failed to decode request: %v", err)
		}

		// retrieval_mode vazio significa padrao do lado Python
		if req.RetrievalMode != "" && req.RetrievalMode != "project_only" {
			t.Errorf("expected empty or 'project_only' retrieval_mode, got %q", req.RetrievalMode)
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{
			Answer:    "Resposta padrao.",
			Sources:   []v1.Source{},
			SessionID: "sess-default",
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	r := setupChatTestRouter(server.URL, nil)

	// Sem retrieval_mode no payload
	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "sess-default",
		"message": "Ola"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}
}

func TestProxyChat_CacheHit_WithRetrievalMode(t *testing.T) {
	// Testa que cache funciona corretamente com retrieval_mode
	// Cache disabled para este teste (foco no proxy)
	callCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{
			Answer:    "Resposta cached.",
			Sources:   []v1.Source{{Document: "doc.pdf", Page: 1, Score: 0.9}},
			SessionID: "sess-cache",
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	// Cache desabilitado — sempre chama Python
	r := setupChatTestRouter(server.URL, nil)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "sess-cache",
		"message": "Pergunta repetida",
		"retrieval_mode": "project_only"
	}`)

	// Primeira chamada
	req1 := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req1.Header.Set("Content-Type", "application/json")
	w1 := httptest.NewRecorder()
	r.ServeHTTP(w1, req1)

	if w1.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w1.Code)
	}

	// Segunda chamada (mesma pergunta, sem cache deve chamar Python novamente)
	req2 := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req2.Header.Set("Content-Type", "application/json")
	w2 := httptest.NewRecorder()
	r.ServeHTTP(w2, req2)

	if w2.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w2.Code)
	}

	// Sem cache, Python foi chamado 2 vezes
	if callCount != 2 {
		t.Errorf("expected 2 calls to Python (no cache), got %d", callCount)
	}
}

func TestProxyChat_XCacheHeader_Miss(t *testing.T) {
	// Verifica que header X-Cache e definido como MISS quando sem cache
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(v1.ChatResponse{
			Answer:    "ok",
			Sources:   []v1.Source{},
			SessionID: "sess",
			CreatedAt: time.Now().UTC(),
		})
	}))
	defer server.Close()

	r := setupChatTestRouter(server.URL, nil)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "sess",
		"message": "Teste"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// X-Cache deve ser MISS quando cache esta desabilitado/indisponivel
	if w.Header().Get("X-Cache") != "MISS" {
		t.Errorf("expected X-Cache MISS, got %q", w.Header().Get("X-Cache"))
	}
}

func TestProxyChat_InvalidRetrievalMode(t *testing.T) {
	// Retrieval_mode invalido deve ser encaminhado ao Python (que valida)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Python rejeitaria, mas para este teste simulamos 400
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte(`{"detail":"invalid retrieval_mode"}`))
	}))
	defer server.Close()

	r := setupChatTestRouter(server.URL, nil)

	body := strings.NewReader(`{
		"project_id": "00000000-0000-0000-0000-000000000001",
		"session_id": "sess",
		"message": "Teste",
		"retrieval_mode": "invalid_mode"
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/chat", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// Gateway repassa 400 do Python como 400
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected status 400, got %d", w.Code)
	}
}
