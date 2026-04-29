# Change: Phase 5 - Public Catalog Indexer

## Why
A Fase 5 expande a base de conhecimento do backend com ingestao de acervo publico (Open Library, Project Gutenberg), construindo pipeline confiavel, rastreavel e idempotente para popular MongoDB, MinIO/S3 e NeonDB/pgvector com livros publicos.

## What Changes
- Bootstrap do servico `public-indexer` (Python/FastAPI) com arquitetura em camadas
- Endpoints administrativos: `GET /health`, `POST /admin/index/run`, `GET /admin/index/jobs/{job_id}`
- Ingestao de catalogo publico com deduplicacao por chaves estaveis (`gutenberg_id`, `ol_key`, hash fallback)
- Download de artefatos com selecao de formato (txt > epub > pdf) e persistencia em MinIO/S3
- Geracao de embeddings publicos com chunking em lote e persistencia no NeonDB/pgvector
- Idempotencia por fingerprint (`source_id + checksum + chunk_version`) e retry seguro com backoff
- Agendamento periodico via `SYNC_INTERVAL_MINUTES` e lock distribuido Redis
- Observabilidade: metricas Prometheus e logs estruturados por `job_id`/`source_id`/`stage`
- **BREAKING**: Resolucao de divergencia de nome de tabela vetorial (`embeddings` -> `document_embeddings`) exige realinhamento de migracao e runtime

## Impact
- Affected specs: `specs/public-catalog-indexer/spec.md`, `specs/data-platform-neondb-pgvector/spec.md`
- Affected code:
  - `services/public-indexer/` (bootstrap completo, substitui estrutura planejada)
  - Migracoes NeonDB (padronizacao de nome de tabela vetorial)
  - `services/python-agent/` (leitura de embeddings publicos - nao escrita nesta fase)
