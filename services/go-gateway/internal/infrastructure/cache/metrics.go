// Package cache implementa cache semantico com Redis para respostas de chat.
package cache

import (
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Metricas Prometheus para observabilidade do cache semantico.
var (
	// semanticCacheHitsTotal conta cache hits por projeto.
	semanticCacheHitsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "semantic_cache_hits_total",
			Help: "Total number of semantic cache hits",
		},
		[]string{"project_id"},
	)

	// semanticCacheMissesTotal conta cache misses por projeto.
	semanticCacheMissesTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "semantic_cache_misses_total",
			Help: "Total number of semantic cache misses",
		},
		[]string{"project_id"},
	)

	// semanticCacheErrorsTotal conta erros Redis por projeto e operacao.
	semanticCacheErrorsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "semantic_cache_errors_total",
			Help: "Total number of semantic cache errors",
		},
		[]string{"project_id", "operation"},
	)

	// semanticCacheLatencySeconds mede latencia das operacoes Redis.
	semanticCacheLatencySeconds = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "semantic_cache_latency_seconds",
			Help:    "Latency of semantic cache operations in seconds",
			Buckets: []float64{0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0},
		},
		[]string{"operation"},
	)

	// semanticCacheHitRatio indica a proporcao de hits por projeto.
	semanticCacheHitRatio = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "semantic_cache_hit_ratio",
			Help: "Ratio of cache hits to total requests per project",
		},
		[]string{"project_id"},
	)
)

// Mapas em memoria para calculo de hit ratio por projeto.
// Protegidos por mutex para concorrencia segura.
var (
	hitsByProject   = make(map[string]float64)
	missesByProject = make(map[string]float64)
	hitsMu          sync.RWMutex
)

// RecordCacheHit registra um cache hit para o projeto informado.
func RecordCacheHit(projectID string) {
	semanticCacheHitsTotal.WithLabelValues(projectID).Inc()

	hitsMu.Lock()
	hitsByProject[projectID]++
	hitsMu.Unlock()
}

// RecordCacheMiss registra um cache miss para o projeto informado.
func RecordCacheMiss(projectID string) {
	semanticCacheMissesTotal.WithLabelValues(projectID).Inc()

	hitsMu.Lock()
	missesByProject[projectID]++
	hitsMu.Unlock()
}

// RecordCacheError registra um erro de cache para o projeto e operacao informados.
func RecordCacheError(projectID, operation string) {
	semanticCacheErrorsTotal.WithLabelValues(projectID, operation).Inc()
}

// RecordCacheLatency registra a latencia de uma operacao de cache.
// operation deve ser "get" ou "set".
func RecordCacheLatency(operation string, duration time.Duration) {
	semanticCacheLatencySeconds.WithLabelValues(operation).Observe(duration.Seconds())
}

// UpdateCacheHitRatio recalcula e atualiza o gauge de hit ratio para o projeto informado.
// Formula: hits / (hits + misses). Se nenhum request, ratio = 0.
func UpdateCacheHitRatio(projectID string) {
	hitsMu.RLock()
	hits := hitsByProject[projectID]
	misses := missesByProject[projectID]
	hitsMu.RUnlock()

	total := hits + misses
	if total == 0 {
		semanticCacheHitRatio.WithLabelValues(projectID).Set(0)
		return
	}

	ratio := hits / total
	semanticCacheHitRatio.WithLabelValues(projectID).Set(ratio)
}
