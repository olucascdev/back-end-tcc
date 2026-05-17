// Package middleware contem middlewares HTTP para o gateway.
package middleware

import (
	"context"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// RequestIDContextKey chave usada para injetar request_id no contexto Go.
// Exportada para que outros pacotes possam extrair o valor.
const RequestIDContextKey = "request_id"

// RequestID gera ou reutiliza um X-Request-ID para cada requisicao.
// Se o header ja estiver presente (ex: propagado de outro servico),
// reutiliza o valor. Caso contrario, gera um UUID novo.
// Adiciona request_id ao contexto Gin E ao contexto Go para propagacao downstream.
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

		// Injeta request_id no contexto Go para propagacao ao cliente Python
		ctx := context.WithValue(c.Request.Context(), RequestIDContextKey, requestID)
		c.Request = c.Request.WithContext(ctx)

		c.Next()
	}
}

// GetRequestID extrai request_id do contexto Go.
// Retorna string vazia se nao encontrado.
func GetRequestID(ctx context.Context) string {
	if id, ok := ctx.Value(RequestIDContextKey).(string); ok {
		return id
	}
	return ""
}
