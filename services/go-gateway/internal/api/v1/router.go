// Package v1 contem o router e handlers da versao 1 da API.
package v1

import (
	"github.com/gin-gonic/gin"

	"github.com/olucasdev/tcc/go-gateway/internal/api/v1/handlers"
	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
	"github.com/olucasdev/tcc/go-gateway/internal/config"
)

// Register registra todos os grupos de rota v1 no router Gin.
func Register(r *gin.Engine, cfg *config.Config) {
	// Inicializar cliente Python (stub por enquanto)
	pythonClient := python.NewClient(cfg.PythonAgentURL, cfg.RequestTimeout)

	// Grupo v1 com prefixo /api/v1
	v1 := r.Group("/api/v1")
	{
		// Health checks - sem autenticacao
		health := v1.Group("/health")
		{
			health.GET("", handlers.Health)
			health.GET("/ready", handlers.Ready)
		}

		// Documents - processamento e operacoes
		docs := v1.Group("/documents")
		{
			docs.POST("/process", handlers.ProxyProcessDocument(pythonClient))
			docs.POST("/summarize", handlers.ProxySummarize(pythonClient))
			docs.POST("/compare", handlers.ProxyCompare(pythonClient))
		}

		// Chat - interacao RAG
		chat := v1.Group("/chat")
		{
			chat.POST("", handlers.ProxyChat(pythonClient))
		}
	}
}
