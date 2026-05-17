# Change: Phase 3 — Semantic Cache & Performance

## Why
O gateway Go ja possui rate limiting in-memory e spec de cache semantico definida, mas sem implementacao real. Phase 3 entrega cache Redis funcional no path de chat, invalidacao por versao de documento, observabilidade de cache e benchmark de ganhos. Tambem avalia migrar rate limiting para Redis para consistencia em deploy multi-instancia.

## What Changes
- **Feature 3.0**: Performance baseline — medir latencia p50/p95 e throughput do chat sem cache como referencia.
- **Feature 3.1**: Redis semantic cache no path de chat — embedding da query, busca por similaridade em Redis, TTL configuravel, bypass em cache miss.
- **Feature 3.2**: Invalidacao por versao de documento do projeto — quando documento e atualizado/removido, entries de cache do projeto sao invalidadas.
- **Feature 3.3**: Cache observability — metricas de hit/miss ratio, latencia de cache, logs de decisao cache hit/miss.
- **Feature 3.4**: Benchmark e evidencia — script de benchmark comparando com/sem cache, documentacao de resultados em `docs/`.
- **Feature 3.5 (opcional)**: Hardening — migrar rate limiting in-memory para Redis para consistencia em multi-instancia.

## Impact
- Affected specs:
  - `ai-gateway-go` (cache semantico, rate limiting Redis)
  - `rag-agent-python` (versionamento de documento para invalidacao)
  - `performance-benchmark` (nova capability)
- Affected code:
  - `services/gateway/internal/infrastructure/cache/` — novo modulo Redis semantic cache
  - `services/gateway/internal/application/` — integracao cache no use case de chat
  - `services/gateway/internal/infrastructure/ratelimit/` — possivel migracao para Redis
  - `services/agent/` — expor versao de documento no response de processamento
  - `scripts/benchmark/` — novo script de benchmark
