// Package middleware contem middlewares HTTP para o gateway.
package middleware

import (
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// RequestID gera ou reutiliza um X-Request-ID para cada requisicao.
// Se o header ja estiver presente (ex: propagado de outro servico),
// reutiliza o valor. Caso contrario, gera um UUID novo.
func RequestID() gin.HandlerFunc {
	return func(c *gin.Context) {
		requestID := c.GetHeader("X-Request-ID")
		if requestID == "" {
			requestID = uuid.New().String()
		}

		// Define no contexto do Gin para uso em handlers downstream
		c.Set("request_id", requestID)

		// Inclui no header de resposta para o cliente
		c.Header("X-Request-ID", requestID)

		c.Next()
	}
}
