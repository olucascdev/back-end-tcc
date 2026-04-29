# Change: Phase 6 — Quality, Evaluation and Hardening

## Why

Phase 5 deixou embeddings públicos prontos mas não consumidos no chat RAG. Phase 6 fecha qualidade, avaliação e hardening para entrega do TCC, garantindo que o sistema atenda critérios acadêmicos e operacionais de resiliência.

## What Changes

- **ADDED** modo de recuperação `project_plus_public` no chat RAG do agente Python, com feature flag e rastreabilidade de source_type
- **ADDED** pipeline de avaliação RAG com métricas acadêmicas (faithfulness, answer relevancy, context precision, context recall) e dataset versionado
- **ADDED** endpoints de benchmark de carga no gateway Go (latência p50/p95/p99, throughput, taxa de erro)
- **ADDED** testes completos: unitários Go, unitários Python, integração e smoke e2e
- **ADDED** comportamento de resiliência sob degradação de dependências no gateway Go
- **ADDED** hardening final de segurança e operações (auth admin, redação de logs, alertas, runbooks)
- **ADDED** quality gates unificados e relatório de compliance com riscos residuais
- **MODIFIED** contrato de request/response do chat para suportar flag de retrieval mode

## Impact

- Affected specs:
  - `rag-agent-python` — novo modo de recuperação, pipeline de avaliação, contrato de chat
  - `ai-gateway-go` — endpoints de benchmark, resiliência sob falha
  - `performance-benchmark` — nova capability de benchmark de carga
  - `backend-governance` — quality gates e compliance
- Affected code:
  - `rag-agent-python` — chat handler, retrieval service, evaluation pipeline
  - `ai-gateway-go` — benchmark handlers, resilience middleware, auth admin
  - `tests/` — suites Go e Python, e2e smoke
  - `docs/` — runbooks e relatório de métricas
