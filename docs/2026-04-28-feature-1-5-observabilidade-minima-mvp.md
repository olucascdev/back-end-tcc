# Feature 1.5 - Observabilidade minima do MVP

## Contexto

Ate a Feature 1.4, o sistema operava sem visibilidade interna. Requests atravessavam o gateway Go e o agente Python sem identificadores rastreaveis, logs eram genericos e nao havia metricas de performance. Em ambiente de producao, isso tornava impossivel:

1. **Rastrear requests entre servicos** — sem `request_id`, um erro no Python-Agent nao podia ser correlacionado com a chamada original no Go Gateway.
2. **Diagnosticar gargalos** — sem metricas de latencia por endpoint, nao era possivel identificar qual operacao degradava sob carga.
3. **Monitorar saude do sistema** — health checks existiam mas nao reportavam status das dependencias (NeonDB, pgvector, OpenAI API).
4. **Auditar operacoes** — logs sem estrutura (apenas `print` ou `logging.info` soltos) impediam filtragem e agregacao em ferramentas externas.

Esta feature resolve:
- propagar `request_id` (UUID) do gateway Go ate o agente Python via headers HTTP
- implementar logs estruturados em JSON com contexto (request_id, endpoint, status, duracao)
- adicionar metricas por endpoint core (latencia p50/p95, error rate, request count)
- estender health checks com verificacao de dependencias
- criar middleware de observabilidade no Go e decorator de metricas no Python

## Decisoes tecnicas

### Propagacao de `request_id` via headers HTTP

Fluxo de propagacao:

```
Cliente → Go Gateway (gera request_id) → HTTP header X-Request-ID → Python-Agent (extrai do header)
```

**Go Gateway**: middleware `ObservabilityMiddleware` gera UUID v4 se o header nao existir, ou reusa o header recebido do cliente. Injeta `request_id` no `gin.Context` via `c.Set("request_id", id)`.

**Python-Agent**: funcao `get_request_id(request)` extrai `X-Request-ID` do header HTTP. Se ausente, gera UUID local. O `request_id` e passado para todos os logs e metricas do request.

**Motivo**: header HTTP e mecanismo padrao de propagacao de contexto entre servicos. Nao exige mudanca nos contratos internos (schemas Pydantic). Compativel com ferramentas de tracing (Jaeger, Zipkin) que leem `X-Request-ID` ou `X-Correlation-ID`.

### Logs estruturados em JSON

Formato de log padronizado:

```json
{
  "level": "info",
  "timestamp": "2026-04-28T14:32:01Z",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "service": "go-gateway",
  "endpoint": "POST /api/v1/documents/process",
  "status": 200,
  "duration_ms": 142,
  "message": "request completed"
}
```

**Go**: middleware captura `request_id`, metodo HTTP, path, status code e duracao. Usa `logrus` com formatter JSON. Campos extras adicionados via `c.Get("request_id")`.

**Python**: decorator `log_request` envolve cada endpoint. Captura `request_id` do header, calcula duracao, registra log JSON via modulo `logging` com `JsonFormatter` customizado.

**Motivo**: logs em JSON sao parseaveis por ferramentas de agregacao (Loki, ELK, Datadog). Campos estruturados permitem filtragem por `request_id`, `status >= 500`, `duration_ms > 1000`.

### Metricas por endpoint core

Metricas coletadas:

| Metrica | Tipo | Descricao |
|---|---|---|
| `http_requests_total` | Counter | Total de requests por endpoint e status |
| `http_request_duration_seconds` | Histogram | Latencia por endpoint (buckets: 0.01, 0.05, 0.1, 0.5, 1, 5, 10s) |
| `http_errors_total` | Counter | Requests com status >= 500 por endpoint |

**Go**: middleware incrementa counters e observa histogram no `prometheus` client. Labels: `method`, `endpoint`, `status`.

**Python**: decorator `track_metrics` usa `prometheus_client` para registrar metricas nos mesmos labels. Endpoint `/metrics` expoe dados no formato Prometheus.

**Endpoints monitorados**:
- Go: `POST /api/v1/documents/process`, `POST /api/v1/chat`, `GET /health`, `GET /ready`
- Python: `POST /api/v1/documents/process`, `POST /api/v1/chat`, `POST /api/v1/summarize`, `POST /api/v1/compare`

**Motivo**: histogramas permitem calcular p50/p95/p99 de latencia. Counters de erro por endpoint identificam operacoes instaveis. Labels consistentes entre Go e Python permitem agregacao cross-service no Prometheus.

### Health checks com dependencias

Endpoint `GET /ready` (readiness probe) verifica:

| Dependencia | Verificacao | Timeout |
|---|---|---|
| NeonDB (PostgreSQL) | `SELECT 1` via connection pool | 2s |
| pgvector | `SELECT extversion FROM pg_extension WHERE extname = 'vector'` | 2s |
| OpenAI API | `client.models.list()` com timeout | 5s |

**Go**: `GET /ready` delega para `GET /health` do Python-Agent via HTTP interno. Se Python responder 200, Go retorna 200. Se Python falhar ou timeout, Go retorna 503.

**Python**: `GET /health` executa verificacoes em paralelo (asyncio.gather). Retorna 200 se todas passarem, 503 se alguma falhar. Response body inclui status de cada dependencia.

**Motivo**: readiness probe com dependencias evita que Kubernetes envie trafego para pods com banco indisponivel ou API key invalida. Timeout curto (2-5s) evita bloqueio prolongado.

### Decorator de observabilidade no Python

Padrao decorator para aplicar logging e metricas em endpoints:

```python
@observe_endpoint("POST /api/v1/documents/process")
async def process_document(request: Request):
    ...
```

O decorator `observe_endpoint(endpoint_name)`:
1. Extrai `request_id` do header
2. Registra log de inicio com `request_id` e `endpoint`
3. Executa a funcao original
4. Calcula duracao
5. Registra log de conclusao com `status`, `duration_ms`
6. Incrementa metricas Prometheus

**Motivo**: decorator centraliza logica de observabilidade. Endpoints mantem foco na regra de negocio. Adicionar observabilidade a novo endpoint = adicionar uma linha.

## Implementacao

### Arquivos criados

#### `cmd/gateway/middleware/observability.go` (novo)
- `ObservabilityMiddleware()` — middleware Gin que gera/reusa `request_id`, registra log estruturado, coleta metricas Prometheus
- Gera UUID v4 via `github.com/google/uuid`
- Injeta `request_id` no `gin.Context` para uso downstream
- Calcula duracao via `time.Since(start)`
- Labels Prometheus: `method`, `endpoint`, `status`

#### `cmd/gateway/middleware/health.go` (novo)
- `HealthMiddleware()` — verifica saude do Python-Agent via HTTP interno
- Timeout configuravel (default 5s)
- Retorna 503 se Python-Agent indisponivel

#### `pkg/observability/logger.go` (novo)
- `NewStructuredLogger(service string)` — configura `logrus` com JSON formatter
- Campos padrao: `service`, `timestamp`, `level`
- Metodo `WithFields(fields map[string]interface{})` para contexto adicional

#### `pkg/observability/metrics.go` (novo)
- `InitMetrics()` — registra counters e histogram no `prometheus` client
- `http_requests_total` (CounterVec)
- `http_request_duration_seconds` (HistogramVec)
- `http_errors_total` (CounterVec)

#### `app/observability/middleware.py` (novo)
- `observe_endpoint(endpoint_name)` — decorator para logging e metricas
- `get_request_id(request)` — extrai `X-Request-ID` do header ou gera UUID
- `JsonFormatter` — formatter customizado para logs em JSON
- `track_metrics(endpoint, method, status, duration)` — registra metricas Prometheus

#### `app/observability/health_check.py` (novo)
- `check_database(settings)` — executa `SELECT 1` no NeonDB
- `check_pgvector(settings)` — verifica extensao pgvector instalada
- `check_openai(settings)` — lista modelos OpenAI com timeout
- `run_health_checks(settings)` — executa todas as verificacoes em paralelo via `asyncio.gather`

#### `tests/test_observability.py` (novo)
- 13 testes cobrindo observabilidade
- Classes de teste: `TestObservabilityMiddleware`, `TestRequestIdPropagation`, `TestStructuredLogging`, `TestMetricsCollection`, `TestHealthChecks`
- Cenarios: geracao de request_id, reuso de header existente, log estruturado com campos corretos, metricas incrementadas, health check com dependencia falhando

### Arquivos modificados

#### `cmd/gateway/main.go` (modificado)
- Adicionado `ObservabilityMiddleware` como primeiro middleware na cadeia
- Adicionado `HealthMiddleware` para endpoint `/ready`
- Import de `pkg/observability` para inicializacao de logger e metricas
- Endpoint `/metrics` expoe dados Prometheus

#### `app/main.py` (modificado)
- Decorator `@observe_endpoint` aplicado em todos os endpoints core
- Endpoint `/health` agora usa `run_health_checks()` para verificacao de dependencias
- Endpoint `/metrics` expoe dados Prometheus
- Import de `app.observability.middleware` e `app.observability.health_check`

#### `app/domain/rag_service.py` (modificado)
- Logs agora incluem `request_id` passado via parametro
- Mensagens de log formatadas para compatibilidade com `JsonFormatter`

#### `app/domain/document_processor.py` (modificado)
- Logs agora incluem `request_id` passado via parametro
- Mensagens de erro incluem contexto adicional (filename, file_size)

## Testes executados

### Suite completa: 96/96 passando

```
======================== 96 passed, 1 warning in 0.81s =========================
```

### Distribuicao por arquivo

| Arquivo de teste | Testes | Cobertura |
|---|---|---|
| `test_api_v1.py` | 6 | Health endpoints, stubs de documents/summarize/compare |
| `test_contracts_v1.py` | 38 | Validacao, serializacao e roundtrip JSON de todos os schemas Pydantic |
| `test_process_document.py` | 14 | Pipeline completo de processamento, componentes unitarios, cenarios de erro |
| `test_chat_rag.py` | 14 | RAGService com/sem contexto, formato de fontes, erro LLM, endpoint API |
| `test_session_persistence.py` | 11 | Repositorios de sessao e conversas, mock de banco |
| `test_observability.py` | 13 | Middleware, request_id, logs estruturados, metricas, health checks |

### Cenarios testados em `test_observability.py`

#### TestObservabilityMiddleware
- `test_generates_request_id_when_header_absent`: header nao existe → UUID gerado, retornado no response
- `test_reuses_existing_request_id`: header `X-Request-ID` presente → mesmo ID retornado
- `test_logs_structured_json`: log output e JSON valido com campos `level`, `timestamp`, `request_id`, `endpoint`, `status`, `duration_ms`

#### TestRequestIdPropagation
- `test_propagates_from_go_to_python`: Go gera ID → header enviado → Python extrai mesmo ID
- `test_python_generates_fallback_when_header_missing`: sem header → Python gera UUID local

#### TestStructuredLogging
- `test_log_includes_service_name`: campo `service` presente e correto (`go-gateway` ou `python-agent`)
- `test_log_includes_error_context`: erro registra campo `error` com mensagem
- `test_duration_ms_is_positive`: `duration_ms` sempre >= 0

#### TestMetricsCollection
- `test_increments_request_counter`: counter `http_requests_total` incrementado apos request
- `test_records_duration_histogram`: histogram `http_request_duration_seconds` registra valor
- `test_increments_error_counter_on_500`: status 500 incrementa `http_errors_total`

#### TestHealthChecks
- `test_health_check_passes_when_all_deps_ok`: todas as dependencias respondem → status 200
- `test_health_check_fails_when_database_down`: `check_database` falha → status 503, body indica `database: unhealthy`

### Warning conhecido
- PyPDF2 emite `DeprecationWarning` recomendando migracao para `pypdf`. Nao afeta funcionalidade.

## Proximos passos

1. **Conclusao da Fase 1**: todas as features basicas implementadas (estrutura, contratos, dados, processamento, integracao Go-Python, RAG com fontes, persistencia de sessao, observabilidade minima).
2. **Fase 2 - Resiliencia Go Gateway**: implementar circuit breaker para chamadas ao Python-Agent, retry com backoff exponencial, rate limiting por IP e por projeto, timeout configuravel por operacao.
3. **Fase 3 - Cache semantico Redis**: cache de embeddings e respostas LLM para queries repetidas, invalidacao por versao de documento.
4. **Fase 4 - Fila de processamento PDF**: fila assincrona para documentos grandes, status de progresso, webhook de notificacao.
5. **Fase 5 - Summarize e Compare reais**: implementar resumo de documentos e comparacao tematica com LLM.
6. **Dashboards Prometheus/Grafana**: criar dashboards para latencia p95, error rate por endpoint, uso de tokens LLM, status de dependencias.
