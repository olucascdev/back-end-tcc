package handlers

import (
	"errors"
	"log/slog"
	"net/http"

	"github.com/gin-gonic/gin"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
)

// ProxyProcessDocument encaminha requisicao de processamento de documento
// para o agente Python via cliente HTTP real.
func ProxyProcessDocument(client *python.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req v1.ProcessDocumentRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return
		}

		requestID := c.GetString("request_id")
		slog.Info("proxy process-document started",
			slog.String("request_id", requestID),
			slog.String("project_id", req.ProjectID.String()),
			slog.String("document_id", req.DocumentID.String()),
		)

		resp, err := client.ProcessDocument(c.Request.Context(), &req)
		if err != nil {
			slog.Error("proxy process-document failed",
				slog.String("request_id", requestID),
				slog.String("project_id", req.ProjectID.String()),
				slog.String("document_id", req.DocumentID.String()),
				slog.String("error", err.Error()),
			)
			handlePythonError(c, err, "process-document")
			return
		}

		slog.Info("proxy process-document completed",
			slog.String("request_id", requestID),
			slog.String("project_id", req.ProjectID.String()),
			slog.String("document_id", req.DocumentID.String()),
			slog.String("status", resp.Status),
		)

		c.JSON(http.StatusAccepted, resp)
	}
}

// ProxyChat encaminha requisicao de chat RAG para o agente Python via cliente HTTP real.
func ProxyChat(client *python.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req v1.ChatRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return
		}

		requestID := c.GetString("request_id")
		slog.Info("proxy chat started",
			slog.String("request_id", requestID),
			slog.String("project_id", req.ProjectID.String()),
			slog.String("session_id", req.SessionID),
		)

		resp, err := client.Chat(c.Request.Context(), &req)
		if err != nil {
			slog.Error("proxy chat failed",
				slog.String("request_id", requestID),
				slog.String("project_id", req.ProjectID.String()),
				slog.String("session_id", req.SessionID),
				slog.String("error", err.Error()),
			)
			handlePythonError(c, err, "chat")
			return
		}

		slog.Info("proxy chat completed",
			slog.String("request_id", requestID),
			slog.String("project_id", req.ProjectID.String()),
			slog.String("session_id", req.SessionID),
			slog.Int("sources_count", len(resp.Sources)),
		)

		c.JSON(http.StatusOK, resp)
	}
}

// ProxySummarize encaminha requisicao de resumo para o agente Python via cliente HTTP real.
func ProxySummarize(client *python.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req v1.SummarizeRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return
		}

		requestID := c.GetString("request_id")
		slog.Info("proxy summarize started",
			slog.String("request_id", requestID),
			slog.String("project_id", req.ProjectID.String()),
			slog.String("document_id", req.DocumentID.String()),
		)

		resp, err := client.Summarize(c.Request.Context(), &req)
		if err != nil {
			slog.Error("proxy summarize failed",
				slog.String("request_id", requestID),
				slog.String("project_id", req.ProjectID.String()),
				slog.String("document_id", req.DocumentID.String()),
				slog.String("error", err.Error()),
			)
			handlePythonError(c, err, "summarize")
			return
		}

		slog.Info("proxy summarize completed",
			slog.String("request_id", requestID),
			slog.String("project_id", req.ProjectID.String()),
			slog.String("document_id", req.DocumentID.String()),
		)

		c.JSON(http.StatusOK, resp)
	}
}

// ProxyCompare encaminha requisicao de comparacao para o agente Python via cliente HTTP real.
func ProxyCompare(client *python.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req v1.CompareRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return
		}

		requestID := c.GetString("request_id")
		slog.Info("proxy compare started",
			slog.String("request_id", requestID),
			slog.String("project_id", req.ProjectID.String()),
			slog.Int("document_count", len(req.DocumentIDs)),
		)

		resp, err := client.Compare(c.Request.Context(), &req)
		if err != nil {
			slog.Error("proxy compare failed",
				slog.String("request_id", requestID),
				slog.String("project_id", req.ProjectID.String()),
				slog.String("error", err.Error()),
			)
			handlePythonError(c, err, "compare")
			return
		}

		slog.Info("proxy compare completed",
			slog.String("request_id", requestID),
			slog.String("project_id", req.ProjectID.String()),
		)

		c.JSON(http.StatusOK, resp)
	}
}

// handlePythonError mapeia erros do cliente Python para status HTTP adequados.
// - ErrTimeout -> 504 Gateway Timeout
// - ErrServiceUnavailable -> 502 Bad Gateway
// - ErrValidation -> 400 Bad Request (detalhes do Python)
// - Outros -> 500 Internal Server Error
// Mensagens de erro sao seguras (sem expor detalhes internos).
// Loga erro de upstream com contexto completo (request_id, operation, error type).
func handlePythonError(c *gin.Context, err error, operation string) {
	requestID := c.GetString("request_id")

	switch {
	case errors.Is(err, python.ErrTimeout):
		slog.Warn("python agent timeout",
			slog.String("operation", operation),
			slog.String("request_id", requestID),
			slog.String("error_type", "timeout"),
		)
		c.JSON(http.StatusGatewayTimeout, gin.H{
			"error": "request timed out while processing",
		})

	case errors.Is(err, python.ErrServiceUnavailable):
		slog.Error("python agent unavailable",
			slog.String("operation", operation),
			slog.String("request_id", requestID),
			slog.String("error_type", "service_unavailable"),
			slog.String("error", err.Error()),
		)
		c.JSON(http.StatusBadGateway, gin.H{
			"error": "upstream service unavailable",
		})

	case errors.Is(err, python.ErrValidation):
		slog.Warn("python agent validation error",
			slog.String("operation", operation),
			slog.String("request_id", requestID),
			slog.String("error_type", "validation"),
		)
		c.JSON(http.StatusBadRequest, gin.H{
			"error": "invalid request: upstream validation failed",
		})

	default:
		slog.Error("unexpected python client error",
			slog.String("operation", operation),
			slog.String("request_id", requestID),
			slog.String("error_type", "unexpected"),
			slog.String("error", err.Error()),
		)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "internal server error",
		})
	}
}
