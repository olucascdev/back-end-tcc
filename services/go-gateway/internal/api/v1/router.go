// Package v1 contem o router e handlers da versao 1 da API.
package v1

import (
	"github.com/gin-gonic/gin"

	"github.com/olucasdev/tcc/go-gateway/internal/api/v1/handlers"
	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
	"github.com/olucasdev/tcc/go-gateway/internal/config"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/cache"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/queue"
	"github.com/olucasdev/tcc/go-gateway/internal/middleware"
)

// Register registra todos os grupos de rota v1 no router Gin.
// Recebe o pythonClient ja criado para compartilhar circuit breaker state com o worker pool.
func Register(r *gin.Engine, cfg *config.Config, q queue.Queue, client *python.Client, semanticCache *cache.SemanticCache) {
	// Grupo v1 com prefixo /api/v1
	v1Group := r.Group("/api/v1")
	{
		// Health checks - sem autenticacao
		health := v1Group.Group("/health")
		{
			health.GET("", handlers.Health)
			health.GET("/ready", handlers.Ready)
		}

		// Documents - processamento e operacoes
		docs := v1Group.Group("/documents")
		{
			docs.POST("/process", handlers.ProxyProcessDocument(client, q))
			docs.GET("/jobs/:job_id", handlers.GetJobStatus(q))
			docs.POST("/summarize", handlers.ProxySummarize(client))
			docs.POST("/compare", handlers.ProxyCompare(client))
			docs.POST("/research/gaps", handlers.ProxyResearchGaps(client))
		}

		// Chat - interacao RAG
		chat := v1Group.Group("/chat")
		{
			chat.POST("", handlers.ProxyChat(client, semanticCache))
		}

		// Admin - operacoes administrativas protegidas por chave
		admin := v1Group.Group("/admin", middleware.AdminAuth(cfg.AdminAPIKey))
		{
			benchmarkRunner := handlers.NewBenchmarkRunner(client)
			admin.POST("/benchmark/load", benchmarkRunner.LoadBenchmark())
			admin.GET("/benchmark/load/:run_id", benchmarkRunner.GetBenchmarkStatus())
			admin.GET("/metrics/internal", handlers.GetInternalMetrics(client, q))
		}
	}
}
