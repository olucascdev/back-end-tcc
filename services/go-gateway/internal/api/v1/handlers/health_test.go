package handlers

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/api/v1"
	"github.com/olucasdev/tcc/go-gateway/internal/config"
)

func setupTestRouter() *gin.Engine {
	gin.SetMode(gin.TestMode)
	cfg := &config.Config{
		ServerPort:     "8080",
		PythonAgentURL: "http://localhost:8000",
		RequestTimeout: 30000000000, // 30s
	}
	r := gin.New()
	r.Use(gin.Recovery())
	v1.Register(r, cfg)
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
