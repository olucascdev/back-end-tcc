// Package app contem a configuracao e inicializacao do servidor Gin.
package app

import (
	"log/slog"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"github.com/olucasdev/tcc/go-gateway/internal/api/v1"
	"github.com/olucasdev/tcc/go-gateway/internal/application/webhook"
	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
	"github.com/olucasdev/tcc/go-gateway/internal/config"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/cache"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/circuitbreaker"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/queue"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/ratelimit"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/retry"
	"github.com/olucasdev/tcc/go-gateway/internal/logger"
	"github.com/olucasdev/tcc/go-gateway/internal/middleware"
)

// Setup inicializa o motor Gin com middlewares, routers, fila PDF e worker pool.
// Retorna o engine e uma funcao de cleanup para encerrar recursos gracefulmente.
func Setup(cfg *config.Config) (*gin.Engine, func()) {
	// Configura logger estruturado JSON
	logger.Setup(nil, slog.LevelInfo) // nil = stdout, nivel INFO explicito

	// Usar gin.New() para controle explicito de middlewares
	r := gin.New()

	// Middlewares globais
	r.Use(gin.Recovery())            // Recover de panics
	r.Use(middleware.RequestID())    // Tracking de requisicoes
	limiter := ratelimit.New(cfg.RateLimitRequests, cfg.RateLimitBurst)
	r.Use(limiter.Middleware())      // Rate limiting por usuario/IP
	r.Use(middleware.CORS())         // CORS para desenvolvimento
	r.Use(middleware.MetricsCollector()) // Metricas Prometheus
	r.Use(middleware.RequestLogger())    // Logging estruturado JSON

	// Endpoint de metricas Prometheus
	r.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// Criar fila de processamento de PDF em memoria
	q := queue.NewMemoryQueue(cfg.PDFQueueSize)

	// Construir mapa de timeouts por operacao a partir do config
	timeouts := map[string]time.Duration{
		"chat":             cfg.TimeoutChat,
		"summarize":        cfg.TimeoutSummarize,
		"compare":          cfg.TimeoutCompare,
		"process-document": cfg.TimeoutProcessDocument,
		"health":           cfg.TimeoutHealth,
	}

	// Inicializar circuit breaker por operacao com parametros configuraveis
	breakers := circuitbreaker.NewBreakerGroup(circuitbreaker.Config{
		MaxRequests:      cfg.CircuitMaxRequests,
		FailureThreshold: cfg.CircuitFailureThreshold,
		Timeout:          cfg.CircuitTimeout,
	})

	// Inicializar politica de retry com erros retryaveis definidos
	retryPolicy := retry.NewPolicy(retry.Config{
		MaxRetries:      cfg.RetryMaxRetries,
		BaseDelay:       cfg.RetryBaseDelay,
		MaxDelay:        cfg.RetryMaxDelay,
		RetryableErrors: []error{python.ErrServiceUnavailable, python.ErrTimeout},
	})

	// Inicializar cliente Python com timeouts, circuit breakers e retry policy
	pythonClient := python.NewClientWithResilience(cfg.PythonAgentURL, timeouts, breakers, retryPolicy)

	// Inicializar cache semantico Redis para respostas de chat
	semanticCache, err := cache.NewSemanticCache(cfg.RedisURL, cfg.CacheTTL, cfg.CacheEnabled)
	if err != nil {
		slog.Warn("failed to initialize semantic cache, continuing without cache", slog.String("error", err.Error()))
		semanticCache = nil
	}

	// Inicializar servico de webhook para notificacao de status ao BFF
	webhookService := webhook.NewService(cfg.WebhookURL, cfg.WebhookSecret)
	if webhookService.IsEnabled() {
		slog.Info("webhook service enabled", slog.String("url", cfg.WebhookURL))
	} else {
		slog.Info("webhook service disabled (WEBHOOK_URL not set)")
	}

	// Criar e iniciar worker pool para processamento assincrono de PDFs
	workerPool := queue.NewWorkerPoolWithWebhook(q, pythonClient, cfg.PDFWorkers, webhookService, semanticCache)
	workerPool.Start()

	// Funcao de cleanup para encerrar worker pool e cache gracefulmente
	cleanup := func() {
		slog.Info("stopping pdf worker pool...")
		workerPool.Stop()
		if semanticCache != nil {
			slog.Info("closing semantic cache connection...")
			semanticCache.Close()
		}
	}

	// Registrar routers v1 com fila de PDF, cliente Python compartilhado e cache semantico
	v1.Register(r, cfg, q, pythonClient, semanticCache)

	return r, cleanup
}
