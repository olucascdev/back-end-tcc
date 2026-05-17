// Package ratelimit implementa rate limiting por token bucket para o gateway.
package ratelimit

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"
)

// RedisLimiter implementa rate limiting distribuido via Redis.
// Usa INCR + EXPIRE em pipeline para contagem por janela de tempo.
type RedisLimiter struct {
	client *redis.Client
	burst  int
	window time.Duration
}

// NewRedisLimiter cria um rate limiter baseado em Redis.
// redisURL: URL de conexao Redis.
// rps: requisicoes por segundo permitidas.
// burst: numero maximo de requisicoes na janela.
func NewRedisLimiter(redisURL string, rps, burst int) (*RedisLimiter, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("failed to parse redis url: %w", err)
	}
	client := redis.NewClient(opts)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("failed to connect to redis: %w", err)
	}

	window := time.Duration(burst) * time.Second / time.Duration(rps)
	if window < time.Second {
		window = time.Second
	}

	return &RedisLimiter{
		client: client,
		burst:  burst,
		window: window,
	}, nil
}

// Middleware retorna gin.HandlerFunc que aplica rate limiting via Redis.
// Fail-open: se Redis falhar, request e permitido com warning log.
func (rl *RedisLimiter) Middleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		if rl.client == nil {
			c.Header("X-RateLimit-Limit", fmt.Sprintf("%d", rl.burst))
			c.Header("X-RateLimit-Remaining", fmt.Sprintf("%d", rl.burst))
			c.Next()
			return
		}

		key := extractKey(c)
		redisKey := "ratelimit:" + key

		ctx, cancel := context.WithTimeout(c.Request.Context(), 2*time.Second)
		defer cancel()

		pipe := rl.client.Pipeline()
		incrCmd := pipe.Incr(ctx, redisKey)
		pipe.Expire(ctx, redisKey, rl.window)
		_, err := pipe.Exec(ctx)

		if err != nil {
			// Fail-open: Redis indisponivel nao deve bloquear trafego
			slog.Warn("redis rate limiter error, allowing request (fail-open)",
				slog.String("key", key),
				slog.String("error", err.Error()))
			c.Next()
			return
		}

		current := incrCmd.Val()
		remaining := rl.burst - int(current)
		if remaining < 0 {
			remaining = 0
		}

		// Headers informativos de cota
		c.Header("X-RateLimit-Limit", fmt.Sprintf("%d", rl.burst))
		c.Header("X-RateLimit-Remaining", fmt.Sprintf("%d", remaining))

		if int(current) > rl.burst {
			rateLimitBlockedTotal.WithLabelValues(key).Inc()
			c.JSON(http.StatusTooManyRequests, gin.H{
				"error":   "rate limit exceeded",
				"message": "too many requests, please try again later",
			})
			c.Abort()
			return
		}

		rateLimitRequestsTotal.WithLabelValues(key).Inc()
		c.Next()
	}
}
