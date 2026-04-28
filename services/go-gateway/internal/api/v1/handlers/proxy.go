package handlers

import (
	"net/http"

	"github.com/gin-gonic/gin"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
)

// ProxyProcessDocument encaminha requisicao de processamento de documento
// para o agente Python. Por enquanto retorna mock.
func ProxyProcessDocument(client *python.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req v1.ProcessDocumentRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return
		}

		// Stub: retornar mock sem chamar Python real
		resp := client.ProcessDocument(c.Request.Context(), &req)
		c.JSON(http.StatusAccepted, resp)
	}
}

// ProxyChat encaminha requisicao de chat RAG para o agente Python.
// Por enquanto retorna mock.
func ProxyChat(client *python.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req v1.ChatRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return
		}

		// Stub: retornar mock sem chamar Python real
		resp := client.Chat(c.Request.Context(), &req)
		c.JSON(http.StatusOK, resp)
	}
}

// ProxySummarize encaminha requisicao de resumo para o agente Python.
// Por enquanto retorna mock.
func ProxySummarize(client *python.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req v1.SummarizeRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return
		}

		// Stub: retornar mock sem chamar Python real
		resp := client.Summarize(c.Request.Context(), &req)
		c.JSON(http.StatusOK, resp)
	}
}

// ProxyCompare encaminha requisicao de comparacao para o agente Python.
// Por enquanto retorna mock.
func ProxyCompare(client *python.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req v1.CompareRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return
		}

		// Stub: retornar mock sem chamar Python real
		resp := client.Compare(c.Request.Context(), &req)
		c.JSON(http.StatusOK, resp)
	}
}
