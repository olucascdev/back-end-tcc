package ratelimit

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

// TestLimiter_AllowWithinLimit verifica que requests dentro do limite sao permitidos.
func TestLimiter_AllowWithinLimit(t *testing.T) {
	// 10 tokens/seg, burst 20
	lim := New(10, 20)

	// Burst permite 20 requests imediatos
	for i := 0; i < 20; i++ {
		if !lim.Allow("test-key") {
			t.Fatalf("request %d dentro do burst deveria ser permitido", i+1)
		}
	}
}

// TestLimiter_AllowExceedsLimit verifica que requests acima do limite sao bloqueados.
func TestLimiter_AllowExceedsLimit(t *testing.T) {
	// 10 tokens/seg, burst 5 (burst pequeno para teste rapido)
	lim := New(10, 5)

	// Consome todos os tokens do burst
	for i := 0; i < 5; i++ {
		if !lim.Allow("exceed-key") {
			t.Fatalf("request %d dentro do burst deveria ser permitido", i+1)
		}
	}

	// Proximo request deve ser bloqueado (burst esgotado, rate 10/s nao repoe instantaneamente)
	if lim.Allow("exceed-key") {
		t.Fatal("request acima do limite deveria ser bloqueado")
	}
}

// TestLimiter_BurstAllowed verifica que o burst maximo e respeitado.
func TestLimiter_BurstAllowed(t *testing.T) {
	// 1 token/seg, burst 3
	lim := New(1, 3)

	// Deve permitir exatamente 3 requests (burst)
	allowed := 0
	for i := 0; i < 10; i++ {
		if lim.Allow("burst-key") {
			allowed++
		}
	}

	if allowed != 3 {
		t.Fatalf("esperado 3 requests permitidos (burst), got %d", allowed)
	}
}

// TestLimiter_IsolationBetweenKeys verifica que chaves diferentes nao interferem.
func TestLimiter_IsolationBetweenKeys(t *testing.T) {
	// 10 tokens/seg, burst 2
	lim := New(10, 2)

	// Esgota tokens da chave A
	lim.Allow("key-a")
	lim.Allow("key-a")

	// Chave A deve estar bloqueada
	if lim.Allow("key-a") {
		t.Fatal("chave A deveria estar bloqueada apos esgotar burst")
	}

	// Chave B deve estar liberada (bucket independente)
	if !lim.Allow("key-b") {
		t.Fatal("chave B deveria estar permitida (bucket independente)")
	}
	if !lim.Allow("key-b") {
		t.Fatal("chave B deveria permitir segundo request (burst=2)")
	}
}

// TestMiddleware_AllowsUnderLimit verifica que requests dentro do limite passam pelo middleware.
func TestMiddleware_AllowsUnderLimit(t *testing.T) {
	gin.SetMode(gin.TestMode)
	// 10 req/s, burst 20 — 5 requests devem passar
	lim := New(10, 20)
	router := gin.New()
	router.Use(lim.Middleware())
	router.GET("/test", func(c *gin.Context) {
		c.String(http.StatusOK, "ok")
	})

	for i := 0; i < 5; i++ {
		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		req.Header.Set("X-User-ID", "user-1")
		req.Header.Set("X-Project-ID", "proj-1")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Fatalf("request %d: esperado status 200, got %d", i+1, w.Code)
		}
	}
}

// TestMiddleware_BlocksOverLimit verifica que requests acima do limite sao bloqueados com 429.
func TestMiddleware_BlocksOverLimit(t *testing.T) {
	gin.SetMode(gin.TestMode)
	// 1 req/s, burst 5 — 50 requests rapidos devem gerar bloqueios
	lim := New(1, 5)
	router := gin.New()
	router.Use(lim.Middleware())
	router.GET("/test", func(c *gin.Context) {
		c.String(http.StatusOK, "ok")
	})

	blocked := 0
	for i := 0; i < 50; i++ {
		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		req.Header.Set("X-User-ID", "user-2")
		req.Header.Set("X-Project-ID", "proj-2")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		if w.Code == http.StatusTooManyRequests {
			blocked++
		}
	}

	if blocked == 0 {
		t.Fatal("esperado pelo menos um request bloqueado com 429")
	}
}

// TestMiddleware_Returns429Payload valida o JSON de erro retornado quando limite excedido.
func TestMiddleware_Returns429Payload(t *testing.T) {
	gin.SetMode(gin.TestMode)
	// 1 req/s, burst 1 — segundo request deve retornar 429 com JSON
	lim := New(1, 1)
	router := gin.New()
	router.Use(lim.Middleware())
	router.GET("/test", func(c *gin.Context) {
		c.String(http.StatusOK, "ok")
	})

	// Primeiro request passa
	req1 := httptest.NewRequest(http.MethodGet, "/test", nil)
	req1.Header.Set("X-User-ID", "user-3")
	req1.Header.Set("X-Project-ID", "proj-3")
	w1 := httptest.NewRecorder()
	router.ServeHTTP(w1, req1)
	if w1.Code != http.StatusOK {
		t.Fatalf("primeiro request deveria passar, got %d", w1.Code)
	}

	// Segundo request deve ser bloqueado
	req2 := httptest.NewRequest(http.MethodGet, "/test", nil)
	req2.Header.Set("X-User-ID", "user-3")
	req2.Header.Set("X-Project-ID", "proj-3")
	w2 := httptest.NewRecorder()
	router.ServeHTTP(w2, req2)

	if w2.Code != http.StatusTooManyRequests {
		t.Fatalf("esperado status 429, got %d", w2.Code)
	}

	// Valida payload JSON
	var body map[string]string
	if err := json.Unmarshal(w2.Body.Bytes(), &body); err != nil {
		t.Fatalf("corpo da resposta deveria ser JSON valido: %v", err)
	}

	if body["error"] != "rate limit exceeded" {
		t.Fatalf("esperado error='rate limit exceeded', got '%s'", body["error"])
	}
	if body["message"] != "too many requests, please try again later" {
		t.Fatalf("esperado message='too many requests...', got '%s'", body["message"])
	}
}
