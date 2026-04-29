package cache

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/redis/go-redis/v9"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
)

// Erros sentinelas para operacoes de cache.
var (
	ErrCacheMiss        = errors.New("cache miss")
	ErrCacheUnavailable = errors.New("cache unavailable")
)

// SemanticCache implementa um cache read-through com Redis para respostas de chat.
type SemanticCache struct {
	redisClient *redis.Client
	ttl         time.Duration
	enabled     bool
}

// NewSemanticCache cria e conecta ao Redis para cache semantico.
func NewSemanticCache(redisURL string, ttl time.Duration, enabled bool) (*SemanticCache, error) {
	if !enabled {
		return &SemanticCache{ttl: ttl, enabled: false}, nil
	}
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("failed to parse redis url: %w", err)
	}
	client := redis.NewClient(opts)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		client.Close()
		return nil, fmt.Errorf("failed to connect to redis: %w", err)
	}
	slog.Info("redis cache connected", slog.String("url", redisURL))
	return &SemanticCache{redisClient: client, ttl: ttl, enabled: true}, nil
}

// Get busca uma resposta de chat no cache Redis.
func (c *SemanticCache) Get(ctx context.Context, key string) (*v1.ChatResponse, error) {
	if !c.enabled || c.redisClient == nil {
		return nil, ErrCacheUnavailable
	}
	data, err := c.redisClient.Get(ctx, key).Bytes()
	if err != nil {
		if errors.Is(err, redis.Nil) {
			return nil, ErrCacheMiss
		}
		slog.Warn("redis get error", slog.String("key", key), slog.String("error", err.Error()))
		return nil, ErrCacheUnavailable
	}
	var resp v1.ChatResponse
	if err := json.Unmarshal(data, &resp); err != nil {
		slog.Warn("failed to deserialize cached response", slog.String("key", key), slog.String("error", err.Error()))
		return nil, ErrCacheMiss
	}
	return &resp, nil
}

// Set armazena uma resposta de chat no cache Redis com TTL.
func (c *SemanticCache) Set(ctx context.Context, key string, resp *v1.ChatResponse) error {
	if !c.enabled || c.redisClient == nil {
		return nil
	}
	data, err := json.Marshal(resp)
	if err != nil {
		slog.Warn("failed to serialize response for cache", slog.String("key", key), slog.String("error", err.Error()))
		return err
	}
	go func() {
		bgCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := c.redisClient.Set(bgCtx, key, data, c.ttl).Err(); err != nil {
			slog.Warn("redis set error (non-fatal)", slog.String("key", key), slog.String("error", err.Error()))
		}
	}()
	return nil
}

// Close encerra a conexao com o Redis.
func (c *SemanticCache) Close() error {
	if c.redisClient != nil {
		return c.redisClient.Close()
	}
	return nil
}

// GetProjectCacheVersion retorna a versao atual do cache para o projeto.
// Usa chave "cache_version:{project_id}". Se inexistente, retorna 0.
func (c *SemanticCache) GetProjectCacheVersion(ctx context.Context, projectID string) (int, error) {
	if !c.enabled || c.redisClient == nil {
		return 0, nil
	}
	v, err := c.redisClient.Get(ctx, "cache_version:"+projectID).Int()
	if err != nil {
		if errors.Is(err, redis.Nil) {
			return 0, nil
		}
		slog.Warn("redis get cache version error",
			slog.String("project_id", projectID),
			slog.String("error", err.Error()),
		)
		return 0, err
	}
	return v, nil
}

// IncrementProjectCacheVersion incrementa a versao do cache para o projeto.
// Usa Redis INCR na chave "cache_version:{project_id}".
// Retorna o novo valor da versao apos incremento.
func (c *SemanticCache) IncrementProjectCacheVersion(ctx context.Context, projectID string) (int, error) {
	if !c.enabled || c.redisClient == nil {
		return 0, nil
	}
	v, err := c.redisClient.Incr(ctx, "cache_version:"+projectID).Result()
	if err != nil {
		slog.Warn("redis increment cache version error",
			slog.String("project_id", projectID),
			slog.String("error", err.Error()),
		)
		return 0, err
	}
	return int(v), nil
}
