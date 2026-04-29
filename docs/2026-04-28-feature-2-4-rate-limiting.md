# Feature 2.4 — Rate Limiting no Gateway Go

## Contexto
Proteger o gateway contra abuso e uso excessivo de recursos, garantindo disponibilidade para todos os usuarios. Rate limiting aplica token bucket por chave (usuario+projeto) com fallback para IP quando headers de identificacao nao estao presentes.

## Decisoes Tecnicas

### Token bucket por chave
- Cada combinacao `user_id:project_id` possui um bucket independente.
- Fallback para `X-User-ID` isolado ou `ClientIP` quando headers ausentes.
- Implementacao usa `golang.org/x/time/rate` — battle-tested, thread-safe.

### Headers de identificacao
- `X-User-ID` e `X-Project-ID` sao padrao do gateway para identificacao de contexto.
- Fallback IP garante protecao mesmo sem autenticacao.

### Headers de resposta
- `X-RateLimit-Limit`: burst maximo configurado.
- `X-RateLimit-Remaining`: tokens restantes no bucket.
- Permite clientes adaptarem comportamento.

### Ordem de middlewares
Recovery → RequestID → RateLimit → CORS → MetricsCollector → RequestLogger

- RateLimit apos RequestID para tracking consistente.
- RateLimit antes de CORS para rejeitar requests abusivos sem processar CORS.
- MetricsCollector apos RateLimit para registrar tambem requests bloqueados (429).

### Configuracao via env vars
- `RATE_LIMIT_REQUESTS` (default 10): tokens por segundo.
- `RATE_LIMIT_BURST` (default 20): pico maximo de tokens acumulados.
- Permite ajuste sem recompilar.

## Implementacao

### Arquivos alterados

#### `internal/config/config.go`
- Adicionados campos `RateLimitRequests` (int) e `RateLimitBurst` (int) ao struct `Config`.
- Carregamento via `RATE_LIMIT_REQUESTS` e `RATE_LIMIT_BURST` com defaults 10 e 20.
- Usa funcao `parseInt` existente.

#### `internal/app/app.go`
- Import do pacote `ratelimit`.
- Criacao do limiter no `Setup`: `ratelimit.New(cfg.RateLimitRequests, cfg.RateLimitBurst)`.
- Middleware inserido na cadeia: `r.Use(limiter.Middleware())`.
- Ordem final: Recovery → RequestID → RateLimit → CORS → MetricsCollector → RequestLogger.

#### `internal/infrastructure/ratelimit/limiter_test.go`
- `TestMiddleware_AllowsUnderLimit`: 5 requests com burst 20, todos passam (200).
- `TestMiddleware_BlocksOverLimit`: 50 requests com burst 5, alguns bloqueados (429).
- `TestMiddleware_Returns429Payload`: valida JSON de erro com campos `error` e `message`.

### Arquivos existentes (sem alteracoes)
- `internal/infrastructure/ratelimit/limiter.go` — implementacao ja completa com `Limiter`, `Allow`, `Middleware`, `extractKey`.

## Testes Executados

```bash
cd services/go-gateway
go test ./internal/infrastructure/ratelimit/... -v
```

Testes esperados:
- `TestLimiter_AllowWithinLimit` — PASS
- `TestLimiter_AllowExceedsLimit` — PASS
- `TestLimiter_BurstAllowed` — PASS
- `TestLimiter_IsolationBetweenKeys` — PASS
- `TestMiddleware_AllowsUnderLimit` — PASS
- `TestMiddleware_BlocksOverLimit` — PASS
- `TestMiddleware_Returns429Payload` — PASS

## Proximos Passos
- Feature 2.5: Semantic cache com Redis (cache de respostas de chat/summarize por embedding similarity).
