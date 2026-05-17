package handlers

import (
	"errors"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/cache"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/circuitbreaker"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/queue"
	"github.com/olucasdev/tcc/go-gateway/internal/logger"
)

// ProxyProcessDocument recebe requisicao de processamento de documento,
// cria um job assincrono e o enfileira para processamento pelo worker pool.
// Retorna 202 Accepted com job_id para consulta de status.
// Se a fila estiver cheia, retorna 503 Service Unavailable.
func ProxyProcessDocument(client *python.Client, q queue.Queue) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req v1.ProcessDocumentRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return
		}

		requestID := c.GetString("request_id")
		slog.Info("proxy process-document enqueueing",
			slog.String("request_id", requestID),
			slog.String("project_id", req.ProjectID.String()),
			slog.String("document_id", req.DocumentID.String()),
		)

		// Criar job assincrono com ID unico
		job := &queue.Job{
			ID:         uuid.New().String(),
			DocumentID: req.DocumentID,
			ProjectID:  req.ProjectID,
			StorageKey: req.StorageKey,
			Status:     queue.StatusPending,
			CreatedAt:  time.Now().UTC(),
			UpdatedAt:  time.Now().UTC(),
		}

		// Enfileirar job para processamento assincrono
		if err := q.Enqueue(job); err != nil {
			if errors.Is(err, queue.ErrQueueFull) {
				slog.Warn("pdf queue full, rejecting request",
					slog.String("request_id", requestID),
					slog.String("project_id", req.ProjectID.String()),
				)
				c.JSON(http.StatusServiceUnavailable, gin.H{
					"error": "pdf processing queue is full, please retry later",
				})
				return
			}
			slog.Error("failed to enqueue pdf job",
				slog.String("request_id", requestID),
				slog.String("error", err.Error()),
			)
			c.JSON(http.StatusInternalServerError, gin.H{
				"error": "internal server error",
			})
			return
		}

		slog.Info("pdf job enqueued successfully",
			slog.String("request_id", requestID),
			slog.String("job_id", job.ID),
			slog.String("project_id", req.ProjectID.String()),
			slog.String("document_id", req.DocumentID.String()),
		)

		// Retornar 202 com informacoes do job para consulta de status
		c.JSON(http.StatusAccepted, gin.H{
			"job_id":      job.ID,
			"status":      job.Status,
			"document_id": job.DocumentID.String(),
			"project_id":  job.ProjectID.String(),
		})
	}
}

// GetJobStatus retorna o status atual de um job de processamento de documento.
// Handler para GET /documents/jobs/:job_id.
func GetJobStatus(q queue.Queue) gin.HandlerFunc {
	return func(c *gin.Context) {
		jobID := c.Param("job_id")
		requestID := c.GetString("request_id")

		job, ok := q.GetJob(jobID)
		if !ok {
			slog.Info("job not found",
				slog.String("request_id", requestID),
				slog.String("job_id", jobID),
			)
			c.JSON(http.StatusNotFound, gin.H{
				"error": "job not found",
			})
			return
		}

		slog.Info("job status retrieved",
			slog.String("request_id", requestID),
			slog.String("job_id", jobID),
			slog.String("status", job.Status),
		)

		resp := gin.H{
			"job_id":     job.ID,
			"status":     job.Status,
			"created_at": job.CreatedAt,
			"updated_at": job.UpdatedAt,
		}

		// Incluir campos opcionais conforme status
		if job.ErrorMessage != nil {
			resp["error_message"] = *job.ErrorMessage
		}
		if job.Result != nil {
			resp["result"] = job.Result
		}

		c.JSON(http.StatusOK, resp)
	}
}

// ProxyChat encaminha requisicao de chat RAG para o agente Python via cliente HTTP real.
// Suporte a cache semantico Redis: consulta cache antes de chamar Python, armazena resposta apos sucesso.
func ProxyChat(client *python.Client, semanticCache *cache.SemanticCache) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req v1.ChatRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return
		}

		requestID := c.GetString("request_id")
		projectID := req.ProjectID.String()
		slog.Info("proxy chat started",
			slog.String("request_id", requestID),
			slog.String("project_id", projectID),
			slog.String("session_id", req.SessionID),
		)

		// Tentar cache semantico antes de chamar Python
		cacheKey := ""
		if semanticCache != nil {
			normalized := cache.NormalizeQuestion(req.Message)

			// Obter versao atual do cache do projeto para invalidacao por documento
			cacheVersion := 0
			v, err := semanticCache.GetProjectCacheVersion(c.Request.Context(), projectID)
			if err == nil {
				cacheVersion = v
			} else {
				slog.Warn("failed to get project cache version, using fallback 0",
					slog.String("project_id", projectID),
					slog.String("error", err.Error()),
				)
			}

			cacheKey = cache.BuildCacheKey(req.ProjectID, normalized, cacheVersion)

			cachedResp, err := semanticCache.Get(c.Request.Context(), cacheKey)
			if err == nil && cachedResp != nil {
				// Cache hit — retornar resposta cached diretamente
				// Extrair question_hash da chave de cache para logging
				hashPart := extractHashFromCacheKey(cacheKey)

				slog.Info("cache hit",
					slog.String("cache_status", "hit"),
					slog.String("cache_key", cacheKey),
					slog.String("question_hash", hashPart),
					slog.Int("cache_version", cacheVersion),
					slog.String("request_id", requestID),
					slog.String("project_id", projectID),
				)
				cache.RecordCacheHit(projectID)
				cache.UpdateCacheHitRatio(projectID)
				c.Header("X-Cache", "HIT")
				c.JSON(http.StatusOK, cachedResp)
				return
			}

			// Cache miss ou indisponivel — logar e prosseguir
			if errors.Is(err, cache.ErrCacheMiss) {
				slog.Info("cache miss",
					slog.String("cache_status", "miss"),
					slog.String("cache_key", cacheKey),
					slog.String("request_id", requestID),
					slog.String("project_id", projectID),
				)
				cache.RecordCacheMiss(projectID)
				cache.UpdateCacheHitRatio(projectID)
			} else if errors.Is(err, cache.ErrCacheUnavailable) {
				slog.Warn("cache unavailable, bypassing",
					slog.String("cache_status", "bypass"),
					slog.String("cache_key", cacheKey),
					slog.String("request_id", requestID),
					slog.String("project_id", projectID),
				)
				cache.RecordCacheError(projectID, "get")
			}
		}

		// Cache miss ou bypass — resposta nao sera cached
		c.Header("X-Cache", "MISS")

		resp, err := client.Chat(c.Request.Context(), &req)
		if err != nil {
			slog.Error("proxy chat failed",
				slog.String("request_id", requestID),
				slog.String("project_id", projectID),
				slog.String("session_id", req.SessionID),
				slog.String("error", err.Error()),
			)
			handlePythonError(c, err, "chat")
			return
		}

		// Armazenar resposta no cache apos sucesso (fire-and-forget)
		if semanticCache != nil && cacheKey != "" {
			_ = semanticCache.Set(c.Request.Context(), cacheKey, resp)
		}

		slog.Info("proxy chat completed",
			slog.String("request_id", requestID),
			slog.String("project_id", projectID),
			slog.String("session_id", req.SessionID),
			slog.Int("sources_count", len(resp.Sources)),
		)

		c.JSON(http.StatusOK, resp)
	}
}

// extractHashFromCacheKey extrai o question_hash de uma chave de cache.
// Formato esperado: "chat:{project_id}:{question_hash}:{version}"
// Retorna a terceira parte (question_hash) ou string vazia se formato invalido.
func extractHashFromCacheKey(cacheKey string) string {
	parts := strings.Split(cacheKey, ":")
	if len(parts) >= 3 {
		return parts[2]
	}
	return ""
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

// ProxyResearchGaps encaminha requisicao de identificacao de lacunas de pesquisa
// para o agente Python via cliente HTTP real.
func ProxyResearchGaps(client *python.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req v1.ResearchGapRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return
		}

		requestID := c.GetString("request_id")
		slog.Info("proxy research-gaps started",
			slog.String("request_id", requestID),
			slog.String("project_id", req.ProjectID.String()),
			slog.String("theme", req.Theme),
		)

		resp, err := client.ResearchGaps(c.Request.Context(), &req)
		if err != nil {
			slog.Error("proxy research-gaps failed",
				slog.String("request_id", requestID),
				slog.String("project_id", req.ProjectID.String()),
				slog.String("error", err.Error()),
			)
			handlePythonError(c, err, "research-gaps")
			return
		}

		slog.Info("proxy research-gaps completed",
			slog.String("request_id", requestID),
			slog.String("project_id", req.ProjectID.String()),
			slog.Int("gaps_count", len(resp.Gaps)),
		)

		c.JSON(http.StatusOK, resp)
	}
}

// handlePythonError mapeia erros do cliente Python para status HTTP adequados.
// - ErrCircuitOpen -> 503 Service Unavailable
// - ErrTimeout -> 504 Gateway Timeout
// - ErrServiceUnavailable -> 502 Bad Gateway
// - ErrNotFound -> 404 Not Found
// - ErrValidation -> 400 Bad Request (detalhes do Python)
// - Outros -> 500 Internal Server Error
// Mensagens de erro sao seguras (sem expor detalhes internos).
// Loga erro de upstream com contexto completo (request_id, operation, error type).
func handlePythonError(c *gin.Context, err error, operation string) {
	requestID := c.GetString("request_id")

	switch {
	case errors.Is(err, circuitbreaker.ErrCircuitOpen):
		slog.Warn("circuit breaker open",
			slog.String("operation", operation),
			slog.String("request_id", requestID),
			slog.String("error_type", "circuit_open"),
		)
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"error": "upstream service temporarily unavailable due to circuit breaker",
		})

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
			slog.String("error", logger.RedactString(err.Error())),
		)
		c.JSON(http.StatusBadGateway, gin.H{
			"error": "upstream service unavailable",
		})

	case errors.Is(err, python.ErrNotFound):
		slog.Warn("python agent resource not found",
			slog.String("operation", operation),
			slog.String("request_id", requestID),
			slog.String("error_type", "not_found"),
		)
		c.JSON(http.StatusNotFound, gin.H{
			"error": "upstream resource not found",
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
			slog.String("error", logger.RedactString(err.Error())),
		)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": "internal server error",
		})
	}
}
