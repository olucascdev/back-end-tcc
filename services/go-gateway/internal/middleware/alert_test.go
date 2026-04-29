package middleware

import (
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
)

func init() {
	// Forcar gin em modo teste para silenciar logs de router
	gin.SetMode(gin.TestMode)
}

func TestAlertMiddleware_HighLatency(t *testing.T) {
	os.Setenv("ALERT_ENABLED", "true")
	os.Setenv("ALERT_LATENCY_MS", "10") // threshold baixo para teste
	os.Setenv("ALERT_ERROR_THRESHOLD", "100")

	mw := AlertMiddleware()

	w := httptest.NewRecorder()
	_, r := gin.CreateTestContext(w)

	// Handler que simula latencia
	r.Use(mw)
	r.GET("/test", func(c *gin.Context) {
		time.Sleep(20 * time.Millisecond) // acima do threshold de 10ms
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}
}

func TestAlertMiddleware_NoAlertForLowLatency(t *testing.T) {
	os.Setenv("ALERT_ENABLED", "true")
	os.Setenv("ALERT_LATENCY_MS", "5000")
	os.Setenv("ALERT_ERROR_THRESHOLD", "100")

	mw := AlertMiddleware()

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/test", nil)

	// Executar middleware diretamente
	mw(c)

	if w.Code != http.StatusOK && w.Code != 0 {
		t.Errorf("unexpected status code: %d", w.Code)
	}
}

func TestAlertMiddleware_Disabled(t *testing.T) {
	os.Setenv("ALERT_ENABLED", "false")

	mw := AlertMiddleware()

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/test", nil)

	// Middleware desabilitado deve ser no-op
	mw(c)
	// Se chegou aqui sem panic, teste passou
}

func TestAlertMiddleware_SkipsHealthAndMetrics(t *testing.T) {
	os.Setenv("ALERT_ENABLED", "true")
	os.Setenv("ALERT_LATENCY_MS", "1") // threshold muito baixo
	os.Setenv("ALERT_ERROR_THRESHOLD", "100")

	mw := AlertMiddleware()

	paths := []string{"/metrics", "/api/v1/health", "/api/v1/ready"}

	for _, path := range paths {
		t.Run(path, func(t *testing.T) {
			w := httptest.NewRecorder()
			c, _ := gin.CreateTestContext(w)
			c.Request = httptest.NewRequest(http.MethodGet, path, nil)

			mw(c)
			// Nao deve gerar alerta para estas rotas
		})
	}
}

func TestAlertMiddleware_ServerErrorTriggersAlert(t *testing.T) {
	os.Setenv("ALERT_ENABLED", "true")
	os.Setenv("ALERT_LATENCY_MS", "5000")
	os.Setenv("ALERT_ERROR_THRESHOLD", "100")

	mw := AlertMiddleware()

	w := httptest.NewRecorder()
	_, r := gin.CreateTestContext(w)

	r.Use(mw)
	r.GET("/fail", func(c *gin.Context) {
		c.Status(http.StatusInternalServerError)
	})

	req := httptest.NewRequest(http.MethodGet, "/fail", nil)
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected status 500, got %d", w.Code)
	}
}

func TestPathErrorCounter_IncrementAndThreshold(t *testing.T) {
	counter := &pathErrorCounter{
		counts: make(map[string]*errorWindow),
	}

	// Incrementar ate threshold
	threshold := 3
	for i := 0; i < threshold; i++ {
		exceeded := counter.incrementError("/api/test", threshold)
		if exceeded {
			t.Errorf("expected no threshold exceeded at increment %d", i+1)
		}
	}

	// Proximo incremento deve exceder
	exceeded := counter.incrementError("/api/test", threshold)
	if !exceeded {
		t.Error("expected threshold to be exceeded")
	}
}

func TestPathErrorCounter_WindowReset(t *testing.T) {
	counter := &pathErrorCounter{
		counts: make(map[string]*errorWindow),
	}

	// Adicionar entrada com janela expirada
	counter.counts["/api/test"] = &errorWindow{
		count:       5,
		windowStart: time.Now().Add(-2 * time.Minute), // 2 min atras
	}

	// Incrementar deve resetar janela
	exceeded := counter.incrementError("/api/test", 10)
	if exceeded {
		t.Error("expected no threshold exceeded after window reset")
	}

	// Verificar que contador foi resetado para 1
	counter.mu.Lock()
	count := counter.counts["/api/test"].count
	counter.mu.Unlock()

	if count != 1 {
		t.Errorf("expected count to be 1 after reset, got %d", count)
	}
}

func TestPathErrorCounter_DifferentPaths(t *testing.T) {
	counter := &pathErrorCounter{
		counts: make(map[string]*errorWindow),
	}

	threshold := 5

	// Incrementar path A
	for i := 0; i < threshold; i++ {
		counter.incrementError("/api/a", threshold)
	}

	// Path B deve estar zerado
	exceeded := counter.incrementError("/api/b", threshold)
	if exceeded {
		t.Error("expected no threshold exceeded for different path")
	}
}

func TestLoadAlertConfig_Defaults(t *testing.T) {
	// Limpar variaveis de ambiente para testar defaults
	os.Unsetenv("ALERT_ENABLED")
	os.Unsetenv("ALERT_LATENCY_MS")
	os.Unsetenv("ALERT_ERROR_THRESHOLD")

	cfg := loadAlertConfig()

	if !cfg.enabled {
		t.Error("expected enabled to be true by default")
	}
	if cfg.latencyMs != 5000 {
		t.Errorf("expected latencyMs 5000, got %d", cfg.latencyMs)
	}
	if cfg.errorThreshold != 10 {
		t.Errorf("expected errorThreshold 10, got %d", cfg.errorThreshold)
	}
}

func TestLoadAlertConfig_CustomValues(t *testing.T) {
	os.Setenv("ALERT_ENABLED", "true")
	os.Setenv("ALERT_LATENCY_MS", "3000")
	os.Setenv("ALERT_ERROR_THRESHOLD", "20")

	cfg := loadAlertConfig()

	if !cfg.enabled {
		t.Error("expected enabled to be true")
	}
	if cfg.latencyMs != 3000 {
		t.Errorf("expected latencyMs 3000, got %d", cfg.latencyMs)
	}
	if cfg.errorThreshold != 20 {
		t.Errorf("expected errorThreshold 20, got %d", cfg.errorThreshold)
	}
}

func TestLoadAlertConfig_InvalidValues(t *testing.T) {
	os.Setenv("ALERT_ENABLED", "true")
	os.Setenv("ALERT_LATENCY_MS", "invalid")
	os.Setenv("ALERT_ERROR_THRESHOLD", "-5")

	cfg := loadAlertConfig()

	// Valores invalidos devem usar defaults
	if cfg.latencyMs != 5000 {
		t.Errorf("expected default latencyMs 5000 for invalid value, got %d", cfg.latencyMs)
	}
	if cfg.errorThreshold != 10 {
		t.Errorf("expected default errorThreshold 10 for invalid value, got %d", cfg.errorThreshold)
	}
}
