# Feature 5.0 e 5.1 - Preflight Tecnico e Bootstrap do Public-Indexer

**Data:** 2026-04-29
**Status:** Implementado

## Contexto

A Fase 5 do projeto introduz o servico `public-indexer` responsavel por ingerir acervo publico (Open Library, Project Gutenberg, Google Books) e produzir embeddings rastreaveis no NeonDB/pgvector. Antes de implementar a indexacao propriamente dita, foi necessario:

1. **Feature 5.0**: Resolver divergencia de nomenclatura entre migracao 002 (tabela `embeddings`) e runtime python-agent (tabela `document_embeddings`).
2. **Feature 5.1**: Criar estrutura base do servico public-indexer com arquitetura em camadas.

## Decisoes Tecnicas

### Feature 5.0 - Unificacao da Tabela de Embeddings

**Problema:** A migracao `002_create_embeddings_table.sql` criava tabela `embeddings`, mas o runtime `pgvector_store.py` do python-agent referencia `document_embeddings`.

**Solucao:**
- Criada migracao `004_unify_embeddings_table.sql` com logica condicional (DO block) que:
  - Renomeia `embeddings` → `document_embeddings` se apenas a primeira existir
  - Cria `document_embeddings` do zero se nenhuma existir
  - Migra dados e remove duplicata se ambas existirem
- Atualizada migracao `002` para usar `document_embeddings` diretamente (evita divergencia em installs fresh)
- Indices renomeados para padrao `idx_document_embeddings_*`

**Contrato de Metadata para Embeddings Publicos:**
O campo JSONB `metadata` deve incluir obrigatoriamente:
| Campo | Tipo | Descricao |
|-------|------|-----------|
| `source_type` | string | Tipo de origem (ex: `public_library`) |
| `source_provider` | string | Provedor (ex: `gutenberg`, `openlibrary`) |
| `source_id` | string | ID unico na fonte original |
| `artifact_key` | string | Chave do artefato no MinIO/S3 |
| `checksum` | string | Hash do conteudo |
| `chunk_version` | int | Versao do chunk (default: 1) |

**Politica de Deduplicacao:**
- Chave estavel de livro: `gutenberg_id` → `ol_key` → hash(title+authors)
- Fingerprint de chunk: `source_id + checksum + chunk_version`

### Feature 5.1 - Bootstrap do Public-Indexer

**Arquitetura em camadas:**
```
app/
├── main.py              # FastAPI app com lifespan events
├── core/
│   ├── config.py        # Pydantic Settings
│   └── logging.py       # JSON logger com request_id
├── api/v1/
│   ├── router.py        # Router principal
│   └── endpoints/
│       ├── health.py    # GET /health, GET /health/ready
│       └── admin.py     # POST /admin/index/run, GET /admin/index/jobs/{job_id}
├── domain/
│   ├── models.py        # IndexerJob, BookMetadata, EmbeddingMetadata
│   └── services.py      # BookCatalogService, JobStore
├── infrastructure/
│   └── clients.py       # PostgreSQL, MongoDB, MinIO, Redis clients
└── application/
    └── usecases.py      # RunIndexUseCase, GetJobStatusUseCase
```

**Dependencias injetadas via `dependency_overrides`** no lifespan, permitindo mocking facil em testes.

**Health check:**
- `GET /api/v1/health` — leve, retorna 200 se servico vivo
- `GET /api/v1/health/ready` — verifica PostgreSQL, MongoDB, MinIO, Redis; retorna 503 se algum falhar

## Implementacao

### Arquivos Criados/Modificados

#### Feature 5.0
| Arquivo | Acao | Descricao |
|---------|------|-----------|
| `infra/migrations/postgres/004_unify_embeddings_table.sql` | Criado | Migracao de unificacao com logica condicional e down migration |
| `infra/migrations/postgres/002_create_embeddings_table.sql` | Modificado | Renomeado `embeddings` → `document_embeddings` e indices |

#### Feature 5.1
| Arquivo | Acao | Descricao |
|---------|------|-----------|
| `services/public-indexer/pyproject.toml` | Criado | Configuracao do projeto Python |
| `services/public-indexer/requirements.txt` | Criado | Dependencias: fastapi, uvicorn, pydantic, psycopg, motor, redis, minio, httpx, prometheus-client |
| `services/public-indexer/app/__init__.py` | Criado | Package init |
| `services/public-indexer/app/main.py` | Criado | FastAPI app com lifespan, dependency injection, middleware |
| `services/public-indexer/app/core/config.py` | Criado | Pydantic Settings com todas as variaveis de ambiente |
| `services/public-indexer/app/core/logging.py` | Criado | JSON formatter + LoggingMiddleware com request_id |
| `services/public-indexer/app/api/v1/router.py` | Criado | Router agregando health e admin |
| `services/public-indexer/app/api/v1/endpoints/health.py` | Criado | Endpoints /health e /health/ready |
| `services/public-indexer/app/api/v1/endpoints/admin.py` | Criado | Endpoints /admin/index/run e /admin/index/jobs/{job_id} |
| `services/public-indexer/app/domain/models.py` | Criado | IndexerJob, BookMetadata, EmbeddingMetadata, JobStatus |
| `services/public-indexer/app/domain/services.py` | Criado | BookCatalogService (MongoDB), JobStore (in-memory) |
| `services/public-indexer/app/infrastructure/clients.py` | Criado | PostgresClient, MongoDBClient, MinIOClient, RedisClient |
| `services/public-indexer/app/application/usecases.py` | Criado | RunIndexUseCase, GetJobStatusUseCase |
| `services/public-indexer/tests/__init__.py` | Criado | Package init |
| `services/public-indexer/tests/test_health.py` | Criado | 6 testes de health/ready com mocks |
| `services/public-indexer/tests/test_admin.py` | Criado | 7 testes de admin endpoints com dependency_overrides |
| `services/public-indexer/Dockerfile` | Criado | Imagem Python 3.11-slim com healthcheck |
| `services/public-indexer/Makefile` | Criado | Targets: install, dev, test, lint, docker-build, docker-run |
| `services/public-indexer/.env.example` | Modificado | Adicionado REDIS_URL e MONGO_DB |
| `services/public-indexer/README.md` | Modificado | Documentacao atualizada com estrutura real e contratos |
| `Makefile` (root) | Modificado | Adicionados targets: lint-indexer, test-indexer, dev-indexer |

## Testes Executados

```
$ pytest services/public-indexer/tests/ -v
13 passed in 0.45s

tests/test_health.py::TestHealthEndpoint::test_health_returns_ok PASSED
tests/test_health.py::TestReadinessEndpoint::test_ready_all_ok PASSED
tests/test_health.py::TestReadinessEndpoint::test_ready_postgres_fails PASSED
tests/test_health.py::TestReadinessEndpoint::test_ready_mongo_fails PASSED
tests/test_health.py::TestReadinessEndpoint::test_ready_minio_fails PASSED
tests/test_health.py::TestReadinessEndpoint::test_ready_redis_fails PASSED
tests/test_admin.py::TestRunIndexEndpoint::test_run_index_returns_job_id PASSED
tests/test_admin.py::TestRunIndexEndpoint::test_run_index_with_dry_run PASSED
tests/test_admin.py::TestRunIndexEndpoint::test_run_index_with_source_filter PASSED
tests/test_admin.py::TestGetJobStatusEndpoint::test_get_job_returns_status PASSED
tests/test_admin.py::TestGetJobStatusEndpoint::test_get_job_not_found PASSED
tests/test_admin.py::TestGetJobStatusEndpoint::test_get_job_completed PASSED
tests/test_admin.py::TestGetJobStatusEndpoint::test_get_job_failed PASSED
```

## Proximos Passos

- **Feature 5.2**: Integrar public-indexer ao docker-compose.yml
- **Feature 5.3**: Implementar clientes de fontes externas (Open Library, Project Gutenberg, Google Books)
- **Feature 5.4**: Geracao de embeddings publicos com chunking e persistencia no pgvector
- **Feature 5.5**: Agendamento periodico (cron/APScheduler) e reprocessamento sem duplicacao

## Riscos Residuais

- Migracao 004 usa DO block com logica condicional — testar em ambiente com dados existentes antes de producao
- JobStore e in-memory — em producao, migrar para Redis ou PostgreSQL para persistencia entre restarts
- Lifespan events conectam todos os clientes sequencialmente — considerar conexoes paralelas para reduzir startup time
