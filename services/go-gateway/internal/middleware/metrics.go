// Package middleware contem middlewares HTTP para o gateway.
package middleware

import (
	"log/slog"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// RequestLogger loga entrada e saida de cada request com duracao em ms.
// Espera que o middleware RequestID() tenha sido executado antes.
func RequestLogger() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()

		requestID, _ := c.Get("request_id")

		slog.Info("Request started",
			slog.String("request_id", requestID.(string)),
			slog.String("method", c.Request.Method),
			slog.String("path", c.Request.URL.Path),
		)

		c.Next()

		durationMs := float64(time.Since(start).Milliseconds())
		statusCode := c.Writer.Status()

		slog.Info("Request completed",
			slog.String("request_id", requestID.(string)),
			slog.String("method", c.Request.Method),
			slog.String("path", c.Request.URL.Path),
			slog.Int("status_code", statusCode),
			slog.Float64("duration_ms", durationMs),
		)
	}
}

// Metricas Prometheus coletadas pelo middleware MetricsCollector.
var (
	requestsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "requests_total",
			Help: "Total number of HTTP requests",
		},
		[]string{"method", "path", "status_code"},
	)

	requestDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "requests_duration_seconds",
			Help:    "HTTP request duration in seconds",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"method", "path", "status_code"},
	)
)

// MetricsCollector coleta latencia e contagem de requests para Prometheus.
func MetricsCollector() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()

		c.Next()

		duration := time.Since(start).Seconds()
		statusCode := strconv.Itoa(c.Writer.Status())
		path := c.Request.URL.Path

		// Ignorar rota de metricas e health para evitar ruido nas metricas
		if path == "/metrics" || path == "/api/v1/health" || path == "/api/v1/ready" {
			return
		}

		requestsTotal.WithLabelValues(c.Request.Method, path, statusCode).Inc()
		requestDuration.WithLabelValues(c.Request.Method, path, statusCode).Observe(duration)
	}
}
