# Feature 2.3 — Retry com Backoff Exponencial

## Contexto

O gateway Go (Feature 2.1: timeout, Feature 2.2: circuit breaker) ja possuia mecanismos de resiliencia para proteger chamadas ao agente Python. No entanto, falhas transitorias (timeout momentaneo, indisponibilidade breve do servico) causavam falha imediata na requisicao do usuario, sem oportunidade de recuperacao automatica.

Esta feature adiciona retry com backoff exponencial e jitter para operacoes idempotentes (Chat, Summarize, Compare), permitindo que falhas transitorias sejam resolvidas automaticamente sem impacto ao usuario final.

## Decisoes Tecnicas

### Retry apenas em operacoes idempotentes
- **Chat, Summarize, Compare**: aplicam retry — sao operacoes de leitura/consulta, idempotentes por natureza.
- **ProcessDocument**: NAO aplica retry — operacao de escrita que pode criar duplicatas se retentada.

### Backoff exponencial com jitter
- Formula: `delay = baseDelay * 2^attempt * jitter`
- Jitter varia entre 50% e 150% do delay calculado
- Delay limitado por `maxDelay` para evitar esperas excessivas
- Jitter previne "thundering herd" quando multiplas instancias retentam simultaneamente

### Erros retryable vs non-retryable
| Erro | Retryable? | Motivacao |
|------|-----------|-----------|
| `ErrTimeout` | Sim | Falha transitoria de rede/latencia |
| `ErrServiceUnavailable` | Sim | Servico Python indisponivel temporariamente |
| `ErrValidation` | Nao | Erro do cliente — retry nao resolve |
| `ErrCircuitOpen` | Nao | Circuit breaker ja gerencia a protecao |

### Camada de retry envolve o circuit breaker
- Ordem: `retry → breaker → HTTP request`
- O retry envolve o breaker para que cada tentativa passe pelo circuito
- Se o circuito abrir durante retries, o breaker retorna `ErrCircuitOpen` (non-retryable) e o retry aborta

### Configuracao via environment variables
- `RETRY_MAX_RETRIES` (default: 3) — numero maximo de tentativas adicionais
- `RETRY_BASE_DELAY` (default: 100ms) — delay inicial
- `RETRY_MAX_DELAY` (default: 2s) — teto do backoff

## Implementacao

### Arquivos alterados

#### `internal/config/config.go`
- Adicionados campos `RetryMaxRetries`, `RetryBaseDelay`, `RetryMaxDelay` ao struct `Config`
- Carregamento via env vars com defaults
- Adicionada funcao helper `parseInt`
- Corrigido fallback de `REQUEST_TIMEOUT` para nao sobrescrever defaults por operacao

#### `internal/client/python/client.go`
- Adicionado campo `retryPolicy *retry.Policy` ao struct `Client`
- Criado `NewClientWithResilience(baseURL, timeouts, breakers, retryPolicy)` — construtor completo
- `NewClient` mantido como wrapper com `retryPolicy=nil` (backward compat)
- `Chat`, `Summarize`, `Compare`: envolvem chamada do breaker com `retryPolicy.Execute` quando policy existe
- `ProcessDocument`: sem alteracao — nunca aplica retry
- Adicionado nil-check em `doRequest` para contexto (corrige teste com nil ctx)

#### `internal/api/v1/router.go`
- Import do pacote `retry`
- Criacao de `retry.Policy` com erros retryable (`ErrServiceUnavailable`, `ErrTimeout`)
- `python.NewClient` → `python.NewClientWithResilience` com retry policy

#### `internal/infrastructure/circuitbreaker/breaker.go`
- Corrigido `State()` para compatibilidade com gobreaker v1.0.0 (retorna 1 valor, nao 2)

### Arquivos criados

#### `internal/infrastructure/retry/policy_test.go`
- `TestPolicy_ExecuteSuccessOnFirstAttempt` — sucesso sem retry
- `TestPolicy_ExecuteSuccessAfterRetries` — sucesso apos 2 retries
- `TestPolicy_ExecuteExhaustedRetries` — falha apos esgotar tentativas
- `TestPolicy_NoRetryForNonRetryableError` — erro non-retryable falha imediatamente
- `TestPolicy_ContextCancelationStopsRetry` — contexto cancelado aborta retry

#### `internal/client/python/client_test.go` (adicoes)
- `TestClient_Chat_RetryOnTimeout` — 2 falhas 503, sucesso na 3a tentativa
- `TestClient_Chat_NoRetryOnValidation` — erro 400 nao retenta
- `TestClient_ProcessDocument_NoRetry` — 503 em process-document nao retenta

## Matriz de Retry por Operacao

| Operacao | Retry? | Erros Retryable |
|----------|--------|-----------------|
| Chat | Sim | Timeout, ServiceUnavailable |
| Summarize | Sim | Timeout, ServiceUnavailable |
| Compare | Sim | Timeout, ServiceUnavailable |
| ProcessDocument | Nao | N/A |
| Health | Nao | N/A |

## Testes Executados

```
go test ./internal/infrastructure/retry/ -v    # 5/5 PASS
go test ./internal/client/python/ -v           # 17/17 PASS (inclui 3 novos)
go test ./internal/config/                     # PASS
go test ./internal/infrastructure/circuitbreaker/ # PASS
go test ./internal/api/v1/handlers/            # PASS (exceto pre-existing bug em Timeout504)
```

## Proximos Passos

- **Feature 2.4**: Cache semantico com Redis para respostas de chat
- Monitorar metricas de retry (tentativas, sucesso/falha por operacao)
- Avaliar ajuste de defaults baseado em dados de producao
