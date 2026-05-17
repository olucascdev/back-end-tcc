## 1. Performance Baseline (Feature 3.0)

- [ ] 1.1 Definir metricas de baseline: latencia p50, p95, p99 e throughput (req/s) para endpoint de chat
- [ ] 1.2 Criar script de benchmark inicial (`scripts/benchmark/baseline.sh`) com k6 ou vegeta
- [ ] 1.3 Executar baseline sem cache e registrar resultados em `docs/phase-3-baseline.md`
- [ ] 1.4 Definir gate de performance: cache MUST reduzir latencia p95 em pelo menos 40% para queries repetidas

## 2. Redis Semantic Cache (Feature 3.1)

- [ ] 2.1 Adicionar dependencia `redis/go-redis` ao gateway Go (se ainda nao presente para cache)
- [ ] 2.2 Criar interface `SemanticCache` em `services/gateway/internal/domain/cache.go`
- [ ] 2.3 Implementar `RedisSemanticCache` em `services/gateway/internal/infrastructure/cache/redis_semantic_cache.go`
  - [ ] 2.3.1 Gerar embedding da query via chamada ao Python agent (endpoint `/v1/embed`) ou modelo local leve
  - [ ] 2.3.2 Armazenar em Redis com chave baseada em project_id + hash do embedding
  - [ ] 2.3.3 Usar Redis vector search (RediSearch/FT) ou abordagem de hash + similaridade por threshold
  - [ ] 2.3.4 TTL configuravel via env (default 1h)
  - [ ] 2.3.5 Serializar resposta completa (answer + sources) como JSON no cache
- [ ] 2.4 Integrar cache no handler de chat do gateway
  - [ ] 2.4.1 Check cache antes de chamar Python agent
  - [ ] 2.4.2 Em cache hit: retornar resposta cached com header `X-Cache: HIT`
  - [ ] 2.4.3 Em cache miss: chamar Python, armazenar resposta no cache, retornar com header `X-Cache: MISS`
  - [ ] 2.4.4 Timeout de cache nao deve bloquear request (fallback para miss)
- [ ] 2.5 Configurar Redis no docker-compose com modulo de busca vetorial ou alternativa
- [ ] 2.6 Testes unitarios para `RedisSemanticCache` com mock de Redis
- [ ] 2.7 Testes de integracao: cache hit, cache miss, cache expirado, Redis indisponivel

## 3. Invalidacao por Versao de Documento (Feature 3.2)

- [ ] 3.1 Adicionar campo `document_version` (int, auto-increment) na tabela `documents` do NeonDB
- [ ] 3.2 Criar migration para adicionar coluna `document_version` com default 1
- [ ] 3.3 Python agent: incrementar versao ao reprocessar documento
- [ ] 3.4 Gateway Go: armazenar `project_document_version` no entry de cache (campo metadata)
- [ ] 3.5 Implementar invalidacao:
  - [ ] 3.5.1 Ao receber webhook de `document_updated`, invalidar todas as entries de cache do projeto
  - [ ] 3.5.2 Usar Redis SCAN ou pattern-based delete para entries do projeto
  - [ ] 3.5.3 Alternativa: incluir versao na chave de cache para invalidacao implicita
- [ ] 3.6 Testes: invalidacao apos update de documento, cache de projeto nao afetado por update de outro projeto

## 4. Cache Observability (Feature 3.3)

- [ ] 4.1 Metricas Prometheus:
  - [ ] 4.1.1 `cache_hits_total` (counter, labels: project_id)
  - [ ] 4.1.2 `cache_misses_total` (counter, labels: project_id)
  - [ ] 4.1.3 `cache_latency_seconds` (histogram)
  - [ ] 4.1.4 `cache_errors_total` (counter, labels: error_type)
  - [ ] 4.1.5 `cache_hit_ratio` (gauge, calculado ou via recording rule)
- [ ] 4.2 Logs estruturados:
  - [ ] 4.2.1 Log cache hit com `cache_status=hit`, `project_id`, `latency_ms`
  - [ ] 4.2.2 Log cache miss com `cache_status=miss`, `project_id`, `reason`
  - [ ] 4.2.3 Log cache error com `cache_status=error`, `error_type`, `fallback=agent`
- [ ] 4.3 Dashboard Prometheus/Grafana (opcional, docker-compose):
  - [ ] 4.3.1 Painel de hit ratio ao longo do tempo
  - [ ] 4.3.2 Painel de latencia p50/p95 com e sem cache
- [ ] 4.4 Testes: validar metricas expostas em `/metrics`, validar formato de logs

## 5. Benchmark e Evidencia (Feature 3.4)

- [ ] 5.1 Criar script de benchmark comparativo (`scripts/benchmark/cache-comparison.sh`)
- [ ] 5.2 Cenario 1: 100 queries unicas (medir baseline sem cache)
- [ ] 5.3 Cenario 2: 100 queries com 50% repetidas (medir ganho de cache)
- [ ] 5.4 Cenario 3: 100 queries com 80% repetidas (medir ganho maximo de cache)
- [ ] 5.5 Documentar resultados em `docs/phase-3-benchmark-results.md` com:
  - [ ] 5.5.1 Tabelas comparativas de latencia p50/p95/p99
  - [ ] 5.5.2 Hit ratio por cenario
  - [ ] 5.5.3 Graficos (se possivel via k6 output ou manual)
  - [ ] 5.5.4 Analise de custo-beneficio (overhead do Redis vs ganho)
- [ ] 5.6 Validar gate de performance: p95 com cache < 60% do p95 sem cache para queries repetidas

## 6. Hardening — Redis Rate Limiting (Feature 3.5 — Opcional)

- [ ] 6.1 Avaliar necessidade: se deploy multi-instancia planejado, migrar para Redis
- [ ] 6.2 Implementar `RedisRateLimiter` em `services/gateway/internal/infrastructure/ratelimit/redis_rate_limiter.go`
  - [ ] 6.2.1 Usar Redis + token bucket ou sliding window via Lua script
  - [ ] 6.2.2 Manter mesma interface de rate limiter existente
  - [ ] 6.2.3 Fallback para in-memory se Redis indisponivel
- [ ] 6.3 Feature flag `RATE_LIMIT_BACKEND=redis|memory` para controle de rollout
- [ ] 6.4 Testes: validar consistencia entre instancias, validar fallback
- [ ] 6.5 Atualizar documentacao em `docs/` com decisao e justificativa

## Critérios de Conclusão da Fase 3

- [ ] Cache semantico Redis operacional no path de chat
- [ ] Invalidacao por versao de documento funcionando
- [ ] Metricas de cache expostas em `/metrics`
- [ ] Logs de cache hit/miss estruturados
- [ ] Benchmark executado com evidencia documentada em `docs/`
- [ ] Gate de performance atingido (p95 reduzido >= 40% para queries repetidas)
- [ ] Testes unitarios e de integracao passando
- [ ] Documentacao da fase em `docs/phase-3-semantic-cache.md` (PT-BR)
