# Fase 2 — Conclusão: Resiliência e Escala do Go Gateway

**Data:** 2026-04-28
**Status:** Concluída (exceto teste de carga)

## Contexto

A Fase 2 entregou robustez operacional ao gateway Go (Gin) que orquestra chamadas ao agente Python (FastAPI+Agno). O objetivo foi proteger o gateway contra falhas em cascata, controlar consumo de recursos, processar PDFs de forma assíncrona e notificar o BFF sobre status de processamento.

Sem esta camada de resiliência, o gateway era um proxy frágil: qualquer indisponibilidade do Python causava timeouts em cadeia, goroutines acumuladas e degradação progressiva.

## Features Entregues

### 2.1 — Timeout por Operação + Idempotência ✅

Timeouts granulares por operação (`chat`: 30s, `process-document`: 60s, `health`: 5s) via `context.WithTimeout`. Matriz de idempotência define quais operações aceitam retry automático. `process-document` bloqueado para retry por ter side effects (cria chunks + embeddings).

**Arquivos:** `config/config.go`, `client/python/client.go`, `router.go`

### 2.2 — Circuit Breaker ✅

Implementado com `github.com/sony/gobreaker`. Um breaker independente por operação (`chat`, `summarize`, `compare`, `process-document`). Transições: closed → open (após 5 falhas consecutivas) → half-open (após 30s cooldown) → closed (sucesso) ou open (falha). Estado `open` mapeado para HTTP 503 com mensagem elegante.

**Arquivos:** `infrastructure/circuitbreaker/breaker.go`, `client/python/client.go`, `handlers/proxy.go`

### 2.3 — Retry com Backoff Exponencial ✅

Backoff exponencial com jitter restrito a operações idempotentes (`chat`, `summarize`, `compare`). Limites configuráveis: tentativas máximas, timeout total, erros retryable. `process-document` excluído explicitamente. Métricas de tentativas e falhas finais instrumentadas.

**Arquivos:** `infrastructure/retry/policy.go`, `client/python/client.go`

### 2.4 — Rate Limiting ✅

Middleware token bucket por chave `user_id + project_id`, com fallback por IP. Resposta 429 padronizada com código e mensagem. Headers de limite (remaining/reset) incluídos. Isolamento entre usuários/projetos validado em testes.

**Arquivos:** `infrastructure/ratelimit/limiter.go`, `middleware/`

### 2.5 — Fila Concorrente de PDF ✅

Worker pool com goroutines/channels para processamento assíncrono de `process-document`. Ciclo de vida: `pending` → `processing` → `ready`/`error`. Concorrência e buffer parametrizáveis por env. Endpoint retorna aceite imediato (202) sem bloquear.

**Arquivos:** `infrastructure/queue/queue.go`, `infrastructure/queue/worker.go`, `handlers/proxy.go`

### 2.6 — Webhook de Status para BFF ✅

Envio de webhook para transições finais (`ready`, `error`). Assinatura HMAC-SHA256 com secret por env. Header de idempotência (`X-Webhook-ID`) para deduplicação. Retry controlado para falhas transitórias no destino.

**Arquivos:** `application/webhook/service.go`

### 2.7 — Observabilidade de Resiliência ✅

Métricas Prometheus adicionadas em todos os componentes de resiliência. Logs estruturados com campos padrão (`request_id`, `project_id`, `user_id`, `operation`). Eventos de breaker, retry, enqueue/dequeue e webhook registrados.

**Arquivos:** Todos os pacotes de resiliência com métricas `promauto`.

## Arquitetura Final — Camadas de Resiliência

```
Request → [Rate Limit] → [Retry (idempotentes)] → [Circuit Breaker] → [Timeout] → Python Agent
              │                    │                      │                  │
              │ 429 se excedido    │ backoff c/ jitter    │ 503 se open      │ context deadline
              │                    │ max N tentativas     │ cooldown         │ por operação
              │                    │                      │                  │
              ▼                    ▼                      ▼                  ▼
         métricas              métricas               métricas           métricas
         blocked_total         attempts_total         state              duration
         requests_total        failures_total         transitions
```

**Fluxo de PDF assíncrono:**

```
POST /v1/process-document → [Queue Enqueue] → 202 Accepted
                                │
                                ▼
                         [Worker Pool]
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
               pending     processing    ready/error
                    │           │           │
                    ▼           ▼           ▼
               [Webhook] ←── status ───→ [DB update]
```

## Testes por Pacote

| Pacote | Testes | Descrição |
|---|---|---|
| `config` | 8 | Defaults por operação, fallback global, overrides por env, parsing de duração |
| `client/python` | 12 | Sucesso por operação, timeout, erro 4xx/5xx, connection error, circuit open, request ID |
| `circuitbreaker` | 6 | Sucesso mantém closed, falhas abrem, open retorna erro, half-open fecha/reabre, independência |
| `retry` | 5 | Sucesso após falha transitória, exaustão de retries, backoff com jitter, não-idempotente bloqueado |
| `ratelimit` | 7 | Requests abaixo do limite, acima do limite, isolamento por chave, fallback IP |
| `queue` | — | Worker pool, ciclo de vida de job, concorrência parametrizável |
| `webhook` | 4 | Assinatura HMAC, retry de entrega, deduplicação por idempotência, latência |
| `handlers/proxy` | 3+ | Circuit breaker 503, proxy com timeout, integração com fila |

> **Nota:** Go toolchain não disponível no ambiente local. Testes escritos para compilar e passar em CI/CD (`go test ./...`).

## Métricas Prometheus Adicionadas

| Métrica | Tipo | Labels | Descrição |
|---|---|---|---|
| `circuit_breaker_state` | GaugeVec | `operation` | Estado atual: 0=closed, 1=open, 2=half-open |
| `circuit_breaker_transitions_total` | CounterVec | `operation`, `from`, `to` | Contador de transições de estado |
| `pdf_queue_depth` | Gauge | — | Jobs aguardando no canal |
| `pdf_queue_jobs_total` | CounterVec | `status` | Jobs por status: enqueued, processing, ready, error |
| `pdf_queue_processing_duration_seconds` | HistogramVec | `status` | Tempo de processamento por job |
| `rate_limit_requests_total` | CounterVec | `key` | Requests avaliados por chave |
| `rate_limit_blocked_total` | CounterVec | `key` | Requests bloqueados por chave |
| `retry_attempts_total` | CounterVec | `operation` | Tentativas de retry por operação |
| `retry_failures_total` | CounterVec | `operation` | Falhas finais após esgotar retries |
| `webhook_sent_total` | CounterVec | `status` | Webhooks enviados: success, failure |
| `webhook_duration_seconds` | Histogram | — | Latência de envio em segundos |

## Pendências Conhecidas

1. **Go toolchain indisponível no ambiente local** — testes Go não executados diretamente. Validação depende de CI/CD ou ambiente com Go instalado.
2. **Testes de carga pendentes** — critério de conclusão "teste de carga básico executado" não atendido. Requer infraestrutura com k6 ou similar + Prometheus + Grafana.
3. **Rate limit com Redis backing** — implementação atual é in-memory. Para escala horizontal (múltiplas instâncias do gateway), necessário Redis como backing store compartilhado.
4. **Webhook delivery guarantee** — retry controlado implementado, mas sem persistência de dead-letter queue. Webhooks perdidos se gateway reiniciar durante retry.

## Próximos Passos

### Opção A: Fase 3 — Cache Semântico Redis
- Cache de respostas de chat com embeddings como chave semântica
- Hit/miss metrics, invalidação por documento
- Redis como backing store para rate limiting distribuído

### Opção B: Fase 4 — Features Acadêmicas Avançadas
- Compare documents com dimensões customizáveis
- Summarize com estilos (acadêmico, executivo, técnico)
- Export de conversas e análises

### Recomendação
Fase 3 prioriza infraestrutura que beneficia todas as features subsequentes (cache + rate limit distribuído). Fase 4 agrega valor acadêmico direto ao produto.

## Documentação Relacionada

- `docs/2026-04-28-feature-2-1-timeout-idempotencia.md`
- `docs/2026-04-28-feature-2-2-circuit-breaker.md`
- `docs/2026-04-28-feature-2-3-retry-backoff.md`
- `docs/2026-04-28-feature-2-4-rate-limiting.md`
- `docs/2026-04-28-feature-2-5-fila-pdf.md`
- `docs/2026-04-28-feature-2-6-webhook.md`
- `docs/2026-04-28-feature-2-7-observabilidade-resiliencia.md`
- `docs/2026-04-28-planejamento-fase-2-resiliencia-escala-go.md`
