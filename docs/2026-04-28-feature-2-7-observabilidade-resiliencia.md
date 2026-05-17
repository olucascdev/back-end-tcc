# Feature 2.7 — Observabilidade de resiliência + métricas

## Contexto

Telemetria operacional dos componentes de resiliência do gateway Go (Features 2.1-2.6).
Métricas Prometheus já existiam para HTTP (`requests_total`, `requests_duration_seconds`).
Esta feature adiciona instrumentação em todos os componentes de resiliência:
circuit breaker, fila PDF, rate limiting, retry e webhook.

## Decisões técnicas

- Usar `promauto` para registro automático de métricas no registrador global.
- Métricas definidas no mesmo pacote do componente que instrumentam (baixo acoplamento).
- Não alterar lógica de negócio — apenas adicionar chamadas de observação.
- Comentários em PT-BR, identificadores em inglês.

## Métricas adicionadas

### Circuit Breaker (`circuitbreaker/breaker.go`)

| Métrica | Tipo | Labels | Descrição |
|---|---|---|---|
| `circuit_breaker_state` | GaugeVec | `operation` | Estado atual: 0=closed, 1=open, 2=half-open |
| `circuit_breaker_transitions_total` | CounterVec | `operation`, `from`, `to` | Contador de transições de estado |

Implementação: callback `OnStateChange` do gobreaker incrementa transição e atualiza gauge.

### Fila PDF (`queue/queue.go`, `queue/worker.go`)

| Métrica | Tipo | Labels | Descrição |
|---|---|---|---|
| `pdf_queue_depth` | Gauge | — | Número de jobs aguardando no canal |
| `pdf_queue_jobs_total` | CounterVec | `status` | Jobs por status: `enqueued`, `processing`, `ready`, `error` |
| `pdf_queue_processing_duration_seconds` | HistogramVec | `status` | Tempo de processamento por job |

Implementação: `Enqueue` incrementa enqueued + atualiza depth. `UpdateStatus` incrementa status counter. `processJob` mede duração total e observa no histograma.

### Rate Limiting (`ratelimit/limiter.go`)

| Métrica | Tipo | Labels | Descrição |
|---|---|---|---|
| `rate_limit_requests_total` | CounterVec | `key` | Total de requests avaliados por chave |
| `rate_limit_blocked_total` | CounterVec | `key` | Requests bloqueados por chave |

Implementação: middleware incrementa `requests_total` para toda requisição e `blocked_total` apenas quando `!allowed`.

### Retry (`retry/policy.go`)

| Métrica | Tipo | Labels | Descrição |
|---|---|---|---|
| `retry_attempts_total` | CounterVec | `operation` | Tentativas de retry por operação |
| `retry_failures_total` | CounterVec | `operation` | Falhas finais após esgotar retries |

Implementação: `Execute` incrementa `retry_attempts_total` em cada iteração do loop. Quando esgota retries, incrementa `retry_failures_total`.

### Webhook (`webhook/service.go`)

| Métrica | Tipo | Labels | Descrição |
|---|---|---|---|
| `webhook_sent_total` | CounterVec | `status` | Webhooks enviados: `success`, `failure` |
| `webhook_duration_seconds` | Histogram | — | Latência de envio em segundos |

Implementação: `SendWebhook` mede duração desde o início, incrementa contador de sucesso ou falha conforme resultado.

## Testes executados

- `go build ./...` — compilação sem erros.
- `go test ./internal/infrastructure/circuitbreaker/` — 6 testes PASS.
- `go test ./internal/infrastructure/ratelimit/` — 7 testes PASS.
- `go test ./internal/infrastructure/retry/` — 5 testes PASS.
- Nenhum teste existente quebrado.

Correções de bugs pré-existentes aplicadas durante build:
- `config.go`: `parseIntWithDefault` chamado com 1 argumento (função exige 2) → trocado para `parseInt`.
- `router.go`: variável `v1Group` indefinida → trocado para `v1`.

## Próximos passos

- Testes de carga com Prometheus + Grafana para validar dashboards.
- Alertas baseados em thresholds (circuit breaker open, fila cheia, retry exhaustion).
- Métricas de cache semântico Redis (Feature 2.8).
