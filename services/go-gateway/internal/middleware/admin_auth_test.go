package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func performRequest(mw gin.HandlerFunc, key string) *httptest.ResponseRecorder {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(mw)
	r.GET("/test", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	if key != "" {
		req.Header.Set("X-Admin-API-Key", key)
	}
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	return w
}

func TestAdminAuth_EmptyKey_AllowsAccess(t *testing.T) {
	mw := AdminAuth("")
	w := performRequest(mw, "")

	if w.Code != http.StatusOK {
		t.Errorf("esperado status %d, obtido %d", http.StatusOK, w.Code)
	}
}

func TestAdminAuth_EmptyKey_IgnoresHeader(t *testing.T) {
	mw := AdminAuth("")
	w := performRequest(mw, "qualquer-coisa")

	if w.Code != http.StatusOK {
		t.Errorf("esperado status %d, obtido %d", http.StatusOK, w.Code)
	}
}

func TestAdminAuth_ValidKey_AllowsAccess(t *testing.T) {
	mw := AdminAuth("secret-key-123")
	w := performRequest(mw, "secret-key-123")

	if w.Code != http.StatusOK {
		t.Errorf("esperado status %d, obtido %d", http.StatusOK, w.Code)
	}
}

func TestAdminAuth_MissingKey_Returns403(t *testing.T) {
	mw := AdminAuth("secret-key-123")
	w := performRequest(mw, "")

	if w.Code != http.StatusForbidden {
		t.Errorf("esperado status %d, obtido %d", http.StatusForbidden, w.Code)
	}
}

func TestAdminAuth_WrongKey_Returns403(t *testing.T) {
	mw := AdminAuth("secret-key-123")
	w := performRequest(mw, "chave-errada")

	if w.Code != http.StatusForbidden {
		t.Errorf("esperado status %d, obtido %d", http.StatusForbidden, w.Code)
	}
}
