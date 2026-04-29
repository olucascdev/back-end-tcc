package middleware

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

// AdminAuth verifica se a chave de administracao fornecida no header
// X-Admin-API-Key corresponde a chave configurada. Se AdminAPIKey estiver
// vazio, permite acesso (fallback para desenvolvimento).
func AdminAuth(adminAPIKey string) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Chave vazia = modo desenvolvimento, permite sem autenticacao
		if adminAPIKey == "" {
			c.Next()
			return
		}

		providedKey := c.GetHeader("X-Admin-API-Key")
		if providedKey == "" || providedKey != adminAPIKey {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
				"error": "forbidden: invalid or missing admin API key",
			})
			return
		}

		c.Next()
	}
}
