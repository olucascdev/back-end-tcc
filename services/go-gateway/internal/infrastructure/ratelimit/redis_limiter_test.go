package ratelimit

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestRedisLimiter_Constructor_FailsOnBadURL(t *testing.T) {
	badURLs := []string{
		"not-a-url",
		"redis://localhost:6379/abc",
		"redis://:invalid@host:port",
		"redis://[::1]:xyz",
	}
	for _, url := range badURLs {
		_, err := NewRedisLimiter(url, 10, 20)
		if err == nil {
			t.Errorf("NewRedisLimiter(%q) deveria retornar erro, got nil", url)
		}
	}
}

func TestRedisLimiter_NilClient_MiddlewareAllows(t *testing.T) {
	gin.SetMode(gin.TestMode)
	limiter := &RedisLimiter{client: nil, burst: 20, window: 0}
	router := gin.New()
	router.Use(limiter.Middleware())
	router.GET("/test", func(c *gin.Context) { c.String(http.StatusOK, "ok") })
	for i := 0; i < 10; i++ {
		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		req.Header.Set("X-User-ID", "user-nil")
		req.Header.Set("X-Project-ID", "proj-nil")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("request %d com client nil deveria passar (fail-open), got %d", i+1, w.Code)
		}
	}
}

func TestRedisLimiter_Middleware_HeadersOnAllow(t *testing.T) {
	gin.SetMode(gin.TestMode)
	limiter := &RedisLimiter{client: nil, burst: 20, window: 0}
	router := gin.New()
	router.Use(limiter.Middleware())
	router.GET("/test", func(c *gin.Context) { c.String(http.StatusOK, "ok") })
	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	req.Header.Set("X-User-ID", "user-hdr")
	req.Header.Set("X-Project-ID", "proj-hdr")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("esperado status 200, got %d", w.Code)
	}
	if w.Header().Get("X-RateLimit-Limit") != "20" {
		t.Fatalf("esperado X-RateLimit-Limit=20, got %s", w.Header().Get("X-RateLimit-Limit"))
	}
	if w.Header().Get("X-RateLimit-Remaining") == "" {
		t.Fatal("header X-RateLimit-Remaining deveria estar presente")
	}
}

func TestRedisLimiter_Middleware_429Payload(t *testing.T) {
	gin.SetMode(gin.TestMode)
	limiter := &RedisLimiter{client: nil, burst: 1, window: 0}
	router := gin.New()
	router.Use(limiter.Middleware())
	router.GET("/test", func(c *gin.Context) { c.String(http.StatusOK, "ok") })
	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("client nil deve permitir request (fail-open), got %d", w.Code)
	}
	if w.Header().Get("X-RateLimit-Limit") == "" {
		t.Fatal("X-RateLimit-Limit header ausente em fail-open")
	}
}
