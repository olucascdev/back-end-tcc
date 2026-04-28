// Package app contem a configuracao e inicializacao do servidor Gin.
package app

import (
	"log/slog"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"github.com/olucasdev/tcc/go-gateway/internal/api/v1"
	"github.com/olucasdev/tcc/go-gateway/internal/config"
	"github.com/olucasdev/tcc/go-gateway/internal/logger"
	"github.com/olucasdev/tcc/go-gateway/internal/middleware"
)

// Setup inicializa o motor Gin com middlewares e routers.
func Setup(cfg *config.Config) *gin.Engine {
	// Configura logger estruturado JSON
	logger.Setup(nil, slog.LevelInfo) // nil = stdout, nivel INFO explicito

	// Usar gin.New() para controle explicito de middlewares
	r := gin.New()

	// Middlewares globais
	r.Use(gin.Recovery())            // Recover de panics
	r.Use(middleware.RequestID())    // Tracking de requisicoes
	r.Use(middleware.CORS())         // CORS para desenvolvimento
	r.Use(middleware.MetricsCollector()) // Metricas Prometheus
	r.Use(middleware.RequestLogger())    // Logging estruturado JSON

	// Endpoint de metricas Prometheus
	r.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// Registrar routers v1
	v1.Register(r, cfg)

	return r
}
