package handlers

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

// Health retorna status basico do servico.
// GET /api/v1/health
func Health(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

// Ready indica que o servico esta pronto para receber requisicoes.
// GET /api/v1/health/ready
func Ready(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "ready"})
}
