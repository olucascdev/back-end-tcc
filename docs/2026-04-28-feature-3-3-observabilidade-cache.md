# Feature 3.3: Observabilidade do Cache Semantico (Metrics + Logs)

## Contexto

Apos implementacao do cache semantico Redis (Feature 3.1) e invalidacao por documento (Feature 3.2), foi necessario adicionar observabilidade para monitorar a eficacia do cache em producao. Sem metricas, nao e possivel avaliar hit rate, latencia do Redis ou identificar problemas de disponibilidade.

## Decisoes Tecnicas

### Metricas Prometheus

Foram definidas 5 metricas no pacote `cache`:

| Metrica | Tipo | Labels | Descricao |
|---------|------|--------|-----------|
| `semantic_cache_hits_total` | CounterVec | `project_id` | Contagem de cache hits por projeto |
| `semantic_cache_misses_total` | CounterVec | `project_id` | Contagem de cache misses por projeto |
| `semantic_cache_errors_total` | CounterVec | `project_id`, `operation` | Erros Redis por projeto e operacao (get/set) |
| `semantic_cache_latency_seconds` | HistogramVec | `operation` | Latencia das operacoes Redis (buckets: 1ms a 1s) |
| `semantic_cache_hit_ratio` | GaugeVec | `project_id` | Proporcao hits/(hits+misses) por projeto |

### Separacao de Responsabilidades

- **`cache.go`**: responsavel apenas por medir latencia das operacoes Redis (`RecordCacheLatency`). Nao tem acesso a `project_id`, entao nao registra hits/misses/erros com esse label.
- **`proxy.go`**: responsavel por registrar hits/misses/erros com contexto completo (`project_id`, `cache_status`, `cache_key`, `question_hash`, `cache_version`).
- **`metrics.go`**: define metricas e funcoes helper exportadas (`RecordCacheHit`, `RecordCacheMiss`, `RecordCacheError`, `RecordCacheLatency`, `UpdateCacheHitRatio`).

### Hit Ratio em Memoria

Como Prometheus counters sao monotonicos, o hit ratio e calculado em memoria:
- Mapas `hitsByProject` e `missesByProject` protegidos por `sync.RWMutex`
- `UpdateCacheHitRatio(projectID)` recalcula `hits / (hits + misses)` a cada hit/miss
- Gauge e atualizado com o valor corrente

### Logs Enriquecidos

Logs de cache no handler `ProxyChat` agora incluem:
- `cache_status`: "hit", "miss" ou "bypass"
- `cache_key`: chave completa do Redis
- `question_hash`: hash SHA256 truncado da pergunta normalizada
- `cache_version`: versao atual do cache do projeto

## Implementacao

### Arquivos Criados

- `services/go-gateway/internal/infrastructure/cache/metrics.go` — definicao de metricas e helpers
- `services/go-gateway/internal/infrastructure/cache/metrics_test.go` — testes unitarios das metricas

### Arquivos Modificados

- `services/go-gateway/internal/infrastructure/cache/cache.go` — adicionado `RecordCacheLatency` em `Get` e `Set`
- `services/go-gateway/internal/api/v1/handlers/proxy.go` — logs enriquecidos com `cache_status`, `question_hash`, `cache_version`; chamadas a `RecordCacheHit/Miss/Error` e `UpdateCacheHitRatio`

### Detalhes de Implementacao

#### `metrics.go`
- Metricas registradas via `promauto` (auto-registro no collector global)
- Funcoes helper sao thread-safe via `sync.RWMutex`
- `extractHashFromCacheKey` em `proxy.go` extrai o hash da chave no formato `chat:{project}:{hash}:{version}`

#### `cache.go`
- `Get`: mede latencia antes de verificar resultado, chama `RecordCacheLatency("get", duration)`
- `Set`: mede latencia dentro da goroutine fire-and-forget, chama `RecordCacheLatency("set", duration)` em ambos os caminhos (sucesso e erro)

#### `proxy.go`
- Cache hit: log com `cache_status="hit"` + `RecordCacheHit` + `UpdateCacheHitRatio`
- Cache miss: log com `cache_status="miss"` + `RecordCacheMiss` + `UpdateCacheHitRatio`
- Cache unavailable: log com `cache_status="bypass"` + `RecordCacheError(projectID, "get")`

## Testes Executados

### Testes Unitarios (`metrics_test.go`)

| Teste | Verificacao |
|-------|-------------|
| `TestRecordCacheHit_DoesNotPanic` | `RecordCacheHit` nao panica com multiplos projetos |
| `TestRecordCacheMiss_DoesNotPanic` | `RecordCacheMiss` nao panica |
| `TestRecordCacheError_DoesNotPanic` | `RecordCacheError` nao panica com operacoes get/set |
| `TestRecordCacheLatency_DoesNotPanic` | `RecordCacheLatency` nao panica |
| `TestUpdateCacheHitRatio_Calculation` | Ratio calculado corretamente (3 hits + 1 miss = 0.75) |
| `TestUpdateCacheHitRatio_ZeroTotal` | Ratio = 0 quando sem requests |
| `TestCacheMetrics_ConcurrentAccess` | 100 goroutines x 10 operacoes sem race conditions |

### Execucao

```bash
cd services/go-gateway
go test ./internal/infrastructure/cache/... -v -race
```

Todos os testes passam sem race conditions.

## Proximos Passos

1. Adicionar dashboard Grafana com as metricas de cache (hit rate por projeto, latencia p50/p95, erros)
2. Configurar alertas para hit rate abaixo de threshold (ex: < 20%)
3. Adicionar metrica de tamanho do payload cached (bytes)
4. Considerar adicionar tracing distribuido (OpenTelemetry) para spans de cache
