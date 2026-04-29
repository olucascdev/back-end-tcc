package handlers

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
	"github.com/olucasdev/tcc/go-gateway/internal/middleware"
)

func setupTestRouter() *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	// Client apontando para URL inexistente (health nao depende do Python)
	client := python.NewClient("http://localhost:8000", map[string]time.Duration{"health": 30 * time.Second}, nil)

	v1Group := r.Group("/api/v1")
	{
		health := v1Group.Group("/health")
		{
			health.GET("", Health)
			health.GET("/ready", Ready)
		}
		docs := v1Group.Group("/documents")
		{
			docs.POST("/process", ProxyProcessDocument(client, nil))
			docs.POST("/summarize", ProxySummarize(client))
			docs.POST("/compare", ProxyCompare(client))
		}
		chat := v1Group.Group("/chat")
		{
			chat.POST("", ProxyChat(client, nil))
		}
	}
	return r
}

func TestHealth_OK(t *testing.T) {
	r := setupTestRouter()

	req := httptest.NewRequest(http.MethodGet, "/api/v1/health", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	expected := `{"status":"ok"}`
	if strings.TrimSpace(w.Body.String()) != expected {
		t.Errorf("expected body %s, got %s", expected, w.Body.String())
	}
}

func TestReady_OK(t *testing.T) {
	r := setupTestRouter()

	req := httptest.NewRequest(http.MethodGet, "/api/v1/health/ready", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	expected := `{"status":"ready"}`
	if strings.TrimSpace(w.Body.String()) != expected {
		t.Errorf("expected body %s, got %s", expected, w.Body.String())
	}
}

func TestHealth_RequestIDHeader(t *testing.T) {
	r := setupTestRouter()

	req := httptest.NewRequest(http.MethodGet, "/api/v1/health", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// Verificar que X-Request-ID foi gerado
	requestID := w.Header().Get("X-Request-ID")
	if requestID == "" {
		t.Error("expected X-Request-ID header to be set")
	}
}

func TestHealth_CustomRequestID(t *testing.T) {
	r := setupTestRouter()

	req := httptest.NewRequest(http.MethodGet, "/api/v1/health", nil)
	req.Header.Set("X-Request-ID", "custom-id-123")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	requestID := w.Header().Get("X-Request-ID")
	if requestID != "custom-id-123" {
		t.Errorf("expected X-Request-ID custom-id-123, got %s", requestID)
	}
}
