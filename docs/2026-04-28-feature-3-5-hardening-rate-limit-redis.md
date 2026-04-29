# Feature 3.5 — Hardening: Rate Limit Distribuído com Redis

## Contexto

O rate limiting do gateway Go/Gin estava implementado exclusivamente em memória
local (token bucket via `golang.org/x/time/rate`). Em cenários multi-instância
(horizontal scaling), cada pod mantém seu próprio contador, permitindo que um
cliente ultrapasse o limite proporcionalmente ao número de réplicas.

Este hardening adiciona um backend Redis opcional para rate limiting
distribuído, permitindo contagem global por chave (usuário:projeto ou IP).

## Decisões Técnicas

| Decisão | Opção | Motivação |
|---------|-------|-----------|
| Algoritmo | INCR + EXPIRE (pipeline Redis) | Simples, atômico, sem dependência extra (Lua scripting ou módulos) |
| Fail-open | Request permitido se Redis falha | Disponibilidade > consistência estrita; gateway não deve bloquear tráfego por dependência |
| Backend selecionável | Env `RATE_LIMIT_BACKEND` | Compatibilidade retroativa; dev local sem Redis |
| Janela | `burst * 1s / rps`, mínimo 1s | Janela proporcional ao burst; evita reset prematuro |
| Timeout Redis | 2s por chamada | Não atrasar o request principal |

## Implementação

### Estrutura

```
internal/infrastructure/ratelimit/
├── limiter.go              # Backend memória (existente)
├── limiter_test.go         # Testes memória (existente)
├── redis_limiter.go        # [NOVO] Backend Redis
└── redis_limiter_test.go   # [NOVO] Testes Redis limiter
```

### `RedisLimiter` — `redis_limiter.go`

- `NewRedisLimiter(redisURL, rps, burst)` — construtor com validação de conexão
- `Middleware()` — Gin middleware que:
  1. Extrai chave via `extractKey()` (mesma função do limiter em memória)
  2. Executa pipeline `INCR` + `EXPIRE` com timeout de 2s
  3. Se Redis falha → log warning + `c.Next()` (fail-open)
  4. Se `current > burst` → 429 + header `X-RateLimit-Remaining: 0`
  5. Headers `X-RateLimit-Limit` e `X-RateLimit-Remaining` sempre presentes

### Interface `rateLimiter` em `app.go`

```go
type rateLimiter interface {
    Middleware() gin.HandlerFunc
}
```

Tanto `*Limiter` (memória) quanto `*RedisLimiter` implementam implicitamente.
A seleção do backend ocorre em `Setup()`:

```go
switch cfg.RateLimitBackend {
case "redis":
    redisLimiter, err := ratelimit.NewRedisLimiter(...)
    if err != nil {
        // fallback para memória com warning
        limiter = ratelimit.New(...)
    } else {
        limiter = redisLimiter
    }
default:
    limiter = ratelimit.New(...)
}
```

### Configuração (`config.go`)

- Novo campo `RateLimitBackend string` (env: `RATE_LIMIT_BACKEND`, default: `"memory"`)

### Variáveis de Ambiente (`.env.example`)

```env
RATE_LIMIT_BACKEND=memory
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_BURST=20
```

### Reutilização de Métricas

O `RedisLimiter` reutiliza os mesmos contadores Prometheus definidos em
`limiter.go`:

- `rate_limit_requests_total{key="..."}`
- `rate_limit_blocked_total{key="..."}`

## Testes Executados

### Testes Unitários (`redis_limiter_test.go`)

| Teste | O que valida |
|-------|-------------|
| `TestRedisLimiter_Constructor_FailsOnBadURL` | URLs inválidas retornam erro |
| `TestRedisLimiter_NilClient_MiddlewareAllows` | Client nil → fail-open (200) |
| `TestRedisLimiter_Middleware_HeadersOnAllow` | Headers X-RateLimit-* presentes |
| `TestRedisLimiter_Middleware_429Payload` | Payload 429 mesmo em cenário fail-open |

### Testes de Integração (pendentes)

- Teste com Redis real via testcontainers
- Teste de concorrência multi-chave
- Teste de failover (Redis offline durante tráfego)

## Próximos Passos

1. Adicionar testcontainers para testes de integração com Redis real
2. Monitorar métricas de erro do Redis limiter (`rate_limiter_redis_errors_total`)
3. Avaliar janela deslizante (sorted set) vs janela fixa (INCR) para cenários
   de pico próximos ao limite da janela
4. Documentar no runbook: "Se RATE_LIMIT_BACKEND=redis e Redis cai, o limiter
   faz fallback silencioso para memória com warning log"
