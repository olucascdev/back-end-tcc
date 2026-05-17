// Package handlers contem os handlers HTTP da API v1.
package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"math"
	"net/http"
	"sort"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/cache"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/queue"
)

// BenchmarkRequest representa o corpo da requisicao de benchmark de carga.
type BenchmarkRequest struct {
	TargetEndpoint  string          `json:"target_endpoint" binding:"required"`
	Concurrency     int             `json:"concurrency" binding:"required,min=1"`
	DurationSeconds int             `json:"duration_seconds" binding:"required,min=1"`
	Payload         json.RawMessage `json:"payload" binding:"required"`
}

// BenchmarkReport representa o resultado de uma execucao de benchmark.
type BenchmarkReport struct {
	RunID         string    `json:"run_id"`
	Status        string    `json:"status"` // "running" | "completed"
	TotalRequests int       `json:"total_requests"`
	Successful    int       `json:"successful"`
	Failed        int       `json:"failed"`
	ErrorRate     float64   `json:"error_rate"`
	Throughput    float64   `json:"throughput"` // requisicoes por segundo
	LatencyP50    float64   `json:"latency_p50_ms"`
	LatencyP95    float64   `json:"latency_p95_ms"`
	LatencyP99    float64   `json:"latency_p99_ms"`
	StartTime     time.Time `json:"start_time"`
	EndTime       time.Time `json:"end_time"`
}

// BenchmarkRunner gerencia execucoes de benchmark de carga.
// Usa mapa em memoria protegido por RWMutex para armazenar relatorios.
type BenchmarkRunner struct {
	client *python.Client
	runs   map[string]*BenchmarkReport
	mu     sync.RWMutex
}

// NewBenchmarkRunner cria um novo BenchmarkRunner vinculado ao cliente Python.
func NewBenchmarkRunner(client *python.Client) *BenchmarkRunner {
	return &BenchmarkRunner{
		client: client,
		runs:   make(map[string]*BenchmarkReport),
	}
}

// LoadBenchmark handler para POST /admin/benchmark/load.
// Valida o corpo da requisicao, cria um run_id, inicia benchmark assincrono
// e retorna 202 Accepted com o run_id para consulta de status.
func (b *BenchmarkRunner) LoadBenchmark() gin.HandlerFunc {
	return func(c *gin.Context) {
		var req BenchmarkRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return
		}

		// Validar target endpoint conhecido
		endpoint := b.mapTargetToEndpoint(req.TargetEndpoint)
		if endpoint == "" {
			c.JSON(http.StatusBadRequest, gin.H{
				"error": "unknown target_endpoint, must be one of: chat, summarize, compare, process-document, research-gaps",
			})
			return
		}

		runID := uuid.New().String()

		// Criar relatorio inicial com status "running"
		report := &BenchmarkReport{
			RunID:     runID,
			Status:    "running",
			StartTime: time.Now().UTC(),
		}

		b.mu.Lock()
		b.runs[runID] = report
		b.mu.Unlock()

		slog.Info("benchmark load started",
			slog.String("run_id", runID),
			slog.String("target", req.TargetEndpoint),
			slog.Int("concurrency", req.Concurrency),
			slog.Int("duration_seconds", req.DurationSeconds),
		)

		// Executar benchmark em background (nao bloqueia a resposta)
		go b.runBenchmark(runID, req, endpoint)

		c.JSON(http.StatusAccepted, gin.H{
			"run_id": runID,
			"status": "accepted",
		})
	}
}

// runBenchmark executa o benchmark de carga em background.
// Cria workers concorrentes que enviam requisicoes HTTP diretas ao agente Python
// durante o periodo especificado. Mede latencia por requisicao e calcula percentuais.
func (b *BenchmarkRunner) runBenchmark(runID string, req BenchmarkRequest, endpoint string) {
	duration := time.Duration(req.DurationSeconds) * time.Second
	deadline := time.Now().Add(duration)

	var (
		wg        sync.WaitGroup
		mu        sync.Mutex
		latencies []float64
		total     int
		success   int
		failed    int
	)

	// Cliente HTTP dedicado para o benchmark (timeout generoso por request individual)
	httpClient := &http.Client{
		Timeout: 60 * time.Second,
	}

	// Criar workers concorrentes
	for i := 0; i < req.Concurrency; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()

			for time.Now().Before(deadline) {
				start := time.Now()

				// Montar requisicao HTTP direta ao agente Python
				httpReq, err := http.NewRequestWithContext(
					context.Background(),
					http.MethodPost,
					b.client.BaseURL()+endpoint,
					bytes.NewReader(req.Payload),
				)
				if err != nil {
					mu.Lock()
					failed++
					total++
					mu.Unlock()
					continue
				}
				httpReq.Header.Set("Content-Type", "application/json")

				resp, err := httpClient.Do(httpReq)
				latencyMs := time.Since(start).Seconds() * 1000

				mu.Lock()
				total++
				if err != nil || resp == nil || resp.StatusCode >= 400 {
					failed++
				} else {
					success++
					latencies = append(latencies, latencyMs)
				}
				mu.Unlock()

				if resp != nil {
					resp.Body.Close()
				}
			}
		}()
	}

	// Aguardar todos os workers concluirem
	wg.Wait()

	// Calcular percentuais de latencia
	sort.Float64s(latencies)
	p50 := percentile(latencies, 50)
	p95 := percentile(latencies, 95)
	p99 := percentile(latencies, 99)

	// Calcular throughput (req/s)
	durationSec := duration.Seconds()
	throughput := float64(total) / durationSec

	// Calcular taxa de erro
	errorRate := 0.0
	if total > 0 {
		errorRate = float64(failed) / float64(total)
	}

	// Atualizar relatorio final
	b.mu.Lock()
	report := b.runs[runID]
	if report != nil {
		report.Status = "completed"
		report.EndTime = time.Now().UTC()
		report.TotalRequests = total
		report.Successful = success
		report.Failed = failed
		report.ErrorRate = math.Round(errorRate*10000) / 10000
		report.Throughput = math.Round(throughput*100) / 100
		report.LatencyP50 = math.Round(p50*100) / 100
		report.LatencyP95 = math.Round(p95*100) / 100
		report.LatencyP99 = math.Round(p99*100) / 100
	}
	b.mu.Unlock()

	slog.Info("benchmark completed",
		slog.String("run_id", runID),
		slog.Int("total_requests", total),
		slog.Int("successful", success),
		slog.Int("failed", failed),
		slog.Float64("throughput_req_s", throughput),
		slog.Float64("error_rate", errorRate),
		slog.Float64("p50_ms", p50),
		slog.Float64("p95_ms", p95),
		slog.Float64("p99_ms", p99),
	)
}

// mapTargetToEndpoint mapeia nome do target para path HTTP do agente Python.
// Retorna string vazia para targets desconhecidos.
func (b *BenchmarkRunner) mapTargetToEndpoint(target string) string {
	switch target {
	case "chat":
		return "/chat"
	case "summarize":
		return "/summarize-document"
	case "compare":
		return "/compare-documents"
	case "process-document":
		return "/process-document"
	case "research-gaps":
		return "/research/gaps"
	default:
		return ""
	}
}

// GetBenchmarkStatus handler para GET /admin/benchmark/load/:run_id.
// Retorna o relatorio do benchmark ou 404 se o run_id nao existir.
func (b *BenchmarkRunner) GetBenchmarkStatus() gin.HandlerFunc {
	return func(c *gin.Context) {
		runID := c.Param("run_id")

		b.mu.RLock()
		report, ok := b.runs[runID]
		b.mu.RUnlock()

		if !ok {
			c.JSON(http.StatusNotFound, gin.H{
				"error": "benchmark run not found",
			})
			return
		}

		c.JSON(http.StatusOK, report)
	}
}

// GetInternalMetrics handler para GET /admin/metrics/internal.
// Retorna metricas internas do gateway: circuit breakers, fila, cache.
func GetInternalMetrics(client *python.Client, q queue.Queue) gin.HandlerFunc {
	return func(c *gin.Context) {
		metrics := gin.H{}

		// Estados dos circuit breakers por operacao
		if states := client.BreakerStates(); states != nil {
			metrics["circuit_breakers"] = states
		}

		// Profundidade da fila de processamento PDF
		if mq, ok := q.(*queue.MemoryQueue); ok {
			metrics["pdf_queue_depth"] = mq.Depth()
		}

		// Proporcao de hit do cache semantico (agregado global)
		metrics["cache_hit_ratio"] = cache.GetGlobalHitRatio()

		c.JSON(http.StatusOK, metrics)
	}
}

// percentile calcula o percentil p de um slice ordenado de latencias em ms.
// Usa interpolacao linear para precisao. Retorna 0 para slice vazio.
func percentile(sorted []float64, p float64) float64 {
	n := len(sorted)
	if n == 0 {
		return 0
	}
	if n == 1 {
		return sorted[0]
	}

	// Posicao fracionaria no slice
	rank := p / 100.0 * float64(n-1)
	lower := int(math.Floor(rank))
	upper := int(math.Ceil(rank))

	if lower == upper {
		return sorted[lower]
	}

	// Interpolacao linear entre valores adjacentes
	frac := rank - float64(lower)
	return sorted[lower]*(1-frac) + sorted[upper]*frac
}
