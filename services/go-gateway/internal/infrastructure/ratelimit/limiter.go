// Package ratelimit implementa rate limiting por token bucket para o gateway.
// Cada chave (user_id:project_id ou IP) possui um bucket independente.
package ratelimit

import (
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"golang.org/x/time/rate"
)

// Metricas Prometheus para rate limiting.
var (
	// rateLimitRequestsTotal — total de requests avaliados por chave.
	rateLimitRequestsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "rate_limit_requests_total",
			Help: "Total number of requests evaluated by rate limiter per key",
		},
		[]string{"key"},
	)

	// rateLimitBlockedTotal — requests bloqueados por chave.
	rateLimitBlockedTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "rate_limit_blocked_total",
			Help: "Total number of requests blocked by rate limiter per key",
		},
		[]string{"key"},
	)
)

// maxLimiters — limite maximo de entradas no mapa antes de triggerar cleanup.
const maxLimiters = 10000

// Limiter gerencia buckets de token bucket por chave.
// Thread-safe via sync.RWMutex.
type Limiter struct {
	mu       sync.Mutex
	limiters map[string]*rate.Limiter
	lastSeen map[string]time.Time // rastreia ultimo acesso para eviction
	rate     rate.Limit
	burst    int
}

// New cria um novo Limiter com taxa e burst configuraveis.
// rate: tokens por segundo permitidos.
// burst: numero maximo de tokens acumulados (pico permitido).
func New(rps int, burst int) *Limiter {
	return &Limiter{
		limiters: make(map[string]*rate.Limiter),
		lastSeen: make(map[string]time.Time),
		rate:     rate.Limit(rps),
		burst:    burst,
	}
}

// getOrCreate retorna o limiter existente para a chave ou cria um novo.
// Deve ser chamado com mu.Lock() mantido.
func (l *Limiter) getOrCreate(key string) *rate.Limiter {
	lim, exists := l.limiters[key]
	if !exists {
		lim = rate.NewLimiter(l.rate, l.burst)
		l.limiters[key] = lim
	}
	l.lastSeen[key] = time.Now()
	return lim
}

// cleanup remove entradas com lastSeen > 1h atras.
// Deve ser chamado com mu.Lock() mantido.
func (l *Limiter) cleanup() {
	cutoff := time.Now().Add(-time.Hour)
	for key, seen := range l.lastSeen {
		if seen.Before(cutoff) {
			delete(l.limiters, key)
			delete(l.lastSeen, key)
		}
	}
}

// Allow consome 1 token para a chave informada.
// Retorna true se o request e permitido, false se excedeu o limite.
func (l *Limiter) Allow(key string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	// Trigger cleanup se mapa exceder limite
	if len(l.limiters) > maxLimiters {
		l.cleanup()
	}

	lim := l.getOrCreate(key)
	return lim.Allow()
}

// Middleware retorna um gin.HandlerFunc que aplica rate limiting.
// Extrai chave de X-User-ID + X-Project-ID ou fallback para IP.
// Responde 429 com JSON padronizado quando limite excedido.
// Adiciona headers X-RateLimit-Limit e X-RateLimit-Remaining.
func (l *Limiter) Middleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		key := extractKey(c)

		// Registrar request avaliado pelo rate limiter
		rateLimitRequestsTotal.WithLabelValues(key).Inc()

		l.mu.Lock()
		// Trigger cleanup se mapa exceder limite — evita crescimento infinito
		if len(l.limiters) > maxLimiters {
			l.cleanup()
		}
		lim := l.getOrCreate(key)
		allowed := lim.Allow()
		// Calcula tokens restantes aproximados
		remaining := int(lim.Tokens())
		l.mu.Unlock()

		// Headers informativos de cota
		c.Header("X-RateLimit-Limit", fmt.Sprintf("%d", l.burst))
		c.Header("X-RateLimit-Remaining", fmt.Sprintf("%d", remaining))

		if !allowed {
			// Registrar request bloqueado
			rateLimitBlockedTotal.WithLabelValues(key).Inc()

			c.JSON(http.StatusTooManyRequests, gin.H{
				"error":   "rate limit exceeded",
				"message": "too many requests, please try again later",
			})
			c.Abort()
			return
		}

		c.Next()
	}
}

// extractKey extrai a chave de rate limit do request.
// Prioridade: X-User-ID:X-Project-ID > X-User-ID > ClientIP.
func extractKey(c *gin.Context) string {
	userID := c.GetHeader("X-User-ID")
	projectID := c.GetHeader("X-Project-ID")

	if userID != "" && projectID != "" {
		return userID + ":" + projectID
	}
	if userID != "" {
		return userID
	}

	// Fallback para IP do cliente
	return c.ClientIP()
}
