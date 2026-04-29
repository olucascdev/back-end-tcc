# Fase 5 — Checklist de Prontidao

**Data:** 2026-04-29
**Fase:** 5 — Indexador de Acervo Publico
**Status:** Pronto para fechamento

## Checklist Tecnico

- [x] Todos os testes passando (173 passed, 2 skipped)
- [x] Migration 004 validada (unificacao `embeddings` → `document_embeddings`)
- [x] OpenSpec validado com `--strict`
- [x] Codigo segue convencoes (nomes ingles, comentarios PT-BR)
- [x] Sem breaking changes nao documentados
- [x] Documentacao PT-BR por feature publicada em `docs/`
- [x] Arquitetura em camadas respeitada (transport / application / domain / infrastructure)
- [x] Contratos de metadata obrigatorios definidos e implementados
- [x] Observabilidade ativa (6 metricas Prometheus + logs JSON + JobReporter)
- [x] Idempotencia garantida por fingerprint
- [x] Retry com backoff+jitter implementado
- [x] Lock distribuido Redis para execucoes concorrentes
- [x] DLQ operacional com retry manual
- [ ] JobStore persistido (recomendacao futura: migrar para Redis/PostgreSQL)
- [ ] Cache incremental de fontes (recomendacao futura: evitar re-processamento desnecessario)

## Artefatos Entregues

### Codigo — Servico Public-Indexer

| Arquivo | Responsabilidade |
|---------|-----------------|
| `services/public-indexer/app/main.py` | FastAPI app com lifespan |
| `services/public-indexer/app/core/config.py` | Pydantic Settings |
| `services/public-indexer/app/core/logging.py` | JSON logger com contextvars |
| `services/public-indexer/app/core/metrics.py` | 6 metricas Prometheus |
| `services/public-indexer/app/api/v1/router.py` | Router principal |
| `services/public-indexer/app/api/v1/endpoints/health.py` | Health e readiness |
| `services/public-indexer/app/api/v1/endpoints/admin.py` | Admin: jobs, DLQ, retry |
| `services/public-indexer/app/domain/models.py` | Modelos de dominio |
| `services/public-indexer/app/infrastructure/clients.py` | Clientes Postgres, MongoDB, MinIO, Redis |
| `services/public-indexer/app/infrastructure/sources/open_library_client.py` | Cliente OpenLibrary |
| `services/public-indexer/app/infrastructure/sources/gutenberg_client.py` | Cliente Gutenberg |
| `services/public-indexer/app/infrastructure/artifact_storage.py` | Armazenamento MinIO |
| `services/public-indexer/app/infrastructure/text_extraction.py` | Extracao de texto |
| `services/public-indexer/app/infrastructure/chunking.py` | Chunking configuravel |
| `services/public-indexer/app/infrastructure/embedder.py` | Geracao de embeddings |
| `services/public-indexer/app/infrastructure/vector_store.py` | Persistencia pgvector |
| `services/public-indexer/app/infrastructure/retry.py` | Backoff + jitter |
| `services/public-indexer/app/infrastructure/scheduler.py` | Agendamento periodico |
| `services/public-indexer/app/infrastructure/dlq.py` | Dead letter queue |
| `services/public-indexer/app/application/usecases.py` | Casos de uso principais |
| `services/public-indexer/app/application/catalog_sync.py` | Sincronizacao de catalogo |
| `services/public-indexer/app/application/artifact_processor.py` | Processamento de artefatos |
| `services/public-indexer/app/application/embedding_processor.py` | Pipeline de embeddings |
| `services/public-indexer/app/application/job_reporter.py` | Relatorio de jobs |

### Codigo — Infraestrutura

| Arquivo | Responsabilidade |
|---------|-----------------|
| `infra/migrations/postgres/004_unify_embeddings_table.sql` | Unificacao da tabela de embeddings |

### Testes

| Diretorio | Cobertura |
|-----------|-----------|
| `services/public-indexer/tests/` | 173 testes (5.0 a 5.6) |

### Documentacao

| Arquivo | Conteudo |
|---------|----------|
| `docs/2026-04-29-fase-5-conclusao-indexador-acervo-publico.md` | Conclusao da fase |
| `docs/2026-04-29-fase-5-readiness-checklist.md` | Este checklist |
| `openspec/changes/add-phase-5-public-catalog-indexer/proposal.md` | Proposta OpenSpec |
| `openspec/changes/add-phase-5-public-catalog-indexer/tasks.md` | Lista de tarefas |
| `openspec/changes/add-phase-5-public-catalog-indexer/design.md` | Decisoes tecnicas |
| `openspec/changes/add-phase-5-public-catalog-indexer/specs/` | Deltas de spec |

## Decisoes de Escopo

### Indexacao apenas, sem consumo RAG nesta fase

- **O que foi feito:** Pipeline completo de ingestao → armazenamento → embeddings → pgvector.
- **O que ficou fora:** Consumo dos embeddings publicos no chat RAG do `python-agent`.
- **Motivo:** Manter escopo focado na producao de dados; consumo RAG sera tratado em fase subsequente.
- **Impacto:** Embeddings publicos existem no banco mas nao sao consultados pelo chat ate a proxima fase.

### JobStore in-memory

- **Decisao:** Manter JobStore em memoria para simplificacao inicial.
- **Risco:** Perda de estado em restart do servico.
- **Mitigacao:** Jobs sao re-criaveis via scheduler; perda e limitada ao job em execucao.
- **Proximo passo:** Migrar para Redis ou PostgreSQL quando persistencia for requisito.

### DLQ em Redis

- **Decisao:** Dead letter queue em Redis para simplicidade operacional.
- **Risco:** Volatilidade em restart critico.
- **Mitigacao:** DLQ monitorada e processada rapidamente; falhas permanentes sao raras.
- **Proximo passo:** Considerar persistencia em PostgreSQL para producao.
