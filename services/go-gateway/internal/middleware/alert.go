// Package middleware contem middlewares HTTP para o gateway.
package middleware

import (
	"log/slog"
	"os"
	"strconv"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
)

// alertConfig armazena configuracoes do sistema de alertas.
type alertConfig struct {
	enabled         bool
	latencyMs       int
	errorThreshold  int
}

// loadAlertConfig carrega configuracoes de alertas a partir de variaveis de ambiente.
func loadAlertConfig() alertConfig {
	cfg := alertConfig{
		enabled:        true,
		latencyMs:      5000,
		errorThreshold: 10,
	}

	if v := os.Getenv("ALERT_ENABLED"); v != "" {
		cfg.enabled = v == "true" || v == "1" || v == "yes"
	}
	if v := os.Getenv("ALERT_LATENCY_MS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			cfg.latencyMs = n
		}
	}
	if v := os.Getenv("ALERT_ERROR_THRESHOLD"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			cfg.errorThreshold = n
		}
	}

	return cfg
}

// pathErrorCounter rastreia contagem de erros por path em janela de 1 minuto.
type pathErrorCounter struct {
	mu       sync.Mutex
	counts   map[string]*errorWindow
}

// errorWindow mantem contagem e timestamp de inicio da janela.
type errorWindow struct {
	count     int
	windowStart time.Time
}

var globalErrorCounter = &pathErrorCounter{
	counts: make(map[string]*errorWindow),
}

// incrementError incrementa o contador de erros para um path.
// Retorna true se o threshold foi excedido na janela atual.
func (p *pathErrorCounter) incrementError(path string, threshold int) bool {
	p.mu.Lock()
	defer p.mu.Unlock()

	now := time.Now()
	window, exists := p.counts[path]

	if !exists || now.Sub(window.windowStart) > time.Minute {
		// Nova janela de 1 minuto
		p.counts[path] = &errorWindow{
			count:       1,
			windowStart: now,
		}
		return false
	}

	window.count++
	return window.count > threshold
}

// AlertMiddleware monitora latencia e taxa de erro por requisicao.
// Gera alertas estruturados quando thresholds sao excedidos.
// Configuravel via variaveis de ambiente:
//   - ALERT_ENABLED: habilita/desabilita o middleware (default: true)
//   - ALERT_LATENCY_MS: threshold de latencia em ms (default: 5000)
//   - ALERT_ERROR_THRESHOLD: threshold de erros por path em 1 min (default: 10)
func AlertMiddleware() gin.HandlerFunc {
	cfg := loadAlertConfig()

	if !cfg.enabled {
		// Retorna no-op middleware quando desabilitado
		return func(c *gin.Context) {
			c.Next()
		}
	}

	return func(c *gin.Context) {
		start := time.Now()

		c.Next()

		durationMs := time.Since(start).Milliseconds()
		statusCode := c.Writer.Status()
		path := c.Request.URL.Path

		// Ignorar rotas de metricas e health para evitar ruido
		if path == "/metrics" || path == "/api/v1/health" || path == "/api/v1/ready" {
			return
		}

		// Alerta de alta latencia
		if int(durationMs) > cfg.latencyMs {
			slog.Warn("alert: high latency detected",
				slog.String("alert_type", "high_latency"),
				slog.String("path", path),
				slog.Int64("duration_ms", durationMs),
				slog.Int("threshold_ms", cfg.latencyMs),
			)
		}

		// Alerta de erro de servidor (5xx)
		if statusCode >= 500 {
			slog.Warn("alert: server error detected",
				slog.String("alert_type", "high_error_rate"),
				slog.String("path", path),
				slog.Int("status_code", statusCode),
			)

			// Verificar se threshold de erros foi excedido
			if globalErrorCounter.incrementError(path, cfg.errorThreshold) {
				slog.Error("alert: error rate threshold exceeded",
					slog.String("alert_type", "error_rate_threshold_exceeded"),
					slog.String("path", path),
					slog.Int("threshold", cfg.errorThreshold),
					slog.String("window", "1m"),
				)
			}
		}
	}
}
