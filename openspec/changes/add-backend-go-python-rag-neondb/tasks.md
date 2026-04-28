# Tasks — FASE 0: Fundação do Backend

> Escopo: estrutura de repositório, infra local, modelagem de dados, contratos internos, bootstrap dos serviços Go e Python, observabilidade e quality gates.
> Cada item ≤ 1-2 dias de trabalho.

---

## 1. Estrutura do Repositório + Infra Local

### 1.1 Criar árvore de diretórios base
- [ ] 1.1.1 Criar pasta `services/gateway/` (Go/Gin)
- [ ] 1.1.2 Criar pasta `services/agent/` (Python/FastAPI+Agno)
- [ ] 1.1.3 Criar pasta `services/indexer/` (Python — catálogo público)
- [ ] 1.1.4 Criar pasta `migrations/` (SQL + Python migração)
- [ ] 1.1.5 Criar pasta `contracts/` (schemas compartilhados: Pydantic JSON + Go DTOs)
- [ ] 1.1.6 Criar pasta `infra/` (docker-compose, configs locais)
- [ ] 1.1.7 Criar pasta `docs/` (documentação PT-BR)
- [ ] 1.1.8 Criar `.gitignore` com padrões Go, Python, env, IDE

### 1.2 Docker Compose local
- [ ] 1.2.1 Serviço PostgreSQL local (simula NeonDB) com extensão `pgvector`
- [ ] 1.2.2 Serviço MongoDB local (catálogo público)
- [ ] 1.2.3 Serviço Redis local (cache semântico + rate limit)
- [ ] 1.2.4 Serviço MinIO local (artefatos PDF)
- [ ] 1.2.5 Network bridge compartilhada entre serviços
- [ ] 1.2.6 Volumes persistentes para dev local
- [ ] 1.2.7 Healthchecks em todos os serviços infra

### 1.3 Arquivos de configuração
- [ ] 1.3.1 Criar `.env.example` com todas as variáveis necessárias (DB, Redis, MinIO, portas, secrets)
- [ ] 1.3.2 Criar `infra/docker-compose.yml` com perfis (`infra`, `gateway`, `agent`, `indexer`)
- [ ] 1.3.3 Criar `Makefile` com targets: `up`, `down`, `migrate`, `test`, `lint`, `build`

---

## 2. Modelagem de Dados + Migrações

### 2.1 NeonDB — Schema relacional
- [ ] 2.1.1 Tabela `users` (id, email, hash_senha, created_at, updated_at)
- [ ] 2.1.2 Tabela `projects` (id, user_id, nome, descricao, created_at, updated_at)
- [ ] 2.1.3 Tabela `documents` (id, project_id, filename, storage_key, status, pages, created_at)
- [ ] 2.1.4 Tabela `conversations` (id, project_id, created_at, updated_at)
- [ ] 2.1.5 Tabela `messages` (id, conversation_id, role, content, created_at)
- [ ] 2.1.6 Índices FK e colunas de busca frequente
- [ ] 2.1.7 Migration `001_initial_schema.up.sql` + `down.sql`

### 2.2 NeonDB/pgvector — Schema vetorial
- [ ] 2.2.1 Tabela `document_chunks` (id, document_id, chunk_text, embedding vector(1536), chunk_index, created_at)
- [ ] 2.2.2 Tabela `public_book_embeddings` (id, book_id, chunk_text, embedding vector(1536), chunk_index, source, created_at)
- [ ] 2.2.3 Índice HNSW ou IVFFlat em `embedding` para busca vetorial
- [ ] 2.2.4 Migration `002_vector_tables.up.sql` + `down.sql`

### 2.3 MongoDB — Catálogo público
- [ ] 2.3.1 Coleção `books` com schema: `{ _id, title, authors, language, subjects, download_url, gutenberg_id, indexed_at }`
- [ ] 2.3.2 Índices em `gutenberg_id` (único), `language`, `subjects`
- [ ] 2.3.3 Script de seed com 5-10 livros de exemplo

### 2.4 Ferramenta de migração
- [ ] 2.4.1 Escolher ferramenta (golang-migrate ou Alembic) e justificar em `docs/`
- [ ] 2.4.2 Configurar pipeline de migração no Makefile
- [ ] 2.4.3 Validar migrações rodando `up` e `down` localmente

---

## 3. Contratos Internos v1

### 3.1 Schemas Pydantic (Python — fonte da verdade)
- [ ] 3.1.1 `ProcessDocumentRequest` (project_id, file_bytes/filename, metadata)
- [ ] 3.1.2 `ProcessDocumentResponse` (document_id, status, pages, chunks_count)
- [ ] 3.1.3 `ChatRequest` (project_id, query, conversation_id?, top_k?)
- [ ] 3.1.4 `ChatResponse` (answer, sources: list[{chunk_text, document_id, score}], conversation_id)
- [ ] 3.1.5 `SummarizeRequest` (document_id, style?)
- [ ] 3.1.6 `SummarizeResponse` (summary: str, key_points: list[str])
- [ ] 3.1.7 `CompareDocumentsRequest` (document_id_a, document_id_b, dimensions?)
- [ ] 3.1.8 `CompareDocumentsResponse` (comparison_table: list[{dimension, doc_a, doc_b, notes}])
- [ ] 3.1.9 `HealthResponse` (status, version, dependencies: dict[str, bool])
- [ ] 3.1.10 `ErrorResponse` (code, message, details?)
- [ ] 3.1.11 Salvar em `contracts/python/schemas.py`

### 3.2 DTOs Go (gateway)
- [ ] 3.2.1 Gerar/espelhar structs Go equivalentes aos schemas Pydantic acima
- [ ] 3.2.2 `ProcessDocumentReq`, `ProcessDocumentRes`
- [ ] 3.2.3 `ChatReq`, `ChatRes`, `Source`
- [ ] 3.2.4 `SummarizeReq`, `SummarizeRes`
- [ ] 3.2.5 `CompareReq`, `CompareRes`, `ComparisonRow`
- [ ] 3.2.6 `HealthRes`, `ErrorRes`
- [ ] 3.2.7 Salvar em `contracts/go/dto/` com package `dto`
- [ ] 3.2.8 Adicionar validação com `go-playground/validator`

### 3.3 Contrato de versionamento
- [ ] 3.3.1 Definir estratégia: URL path versioning (`/v1/...`)
- [ ] 3.3.2 Documentar em `contracts/VERSIONING.md`
- [ ] 3.3.3 Registrar versão atual `v1` em ambos os serviços

---

## 4. Bootstrap Python/FastAPI (Serviço Agent)

### 4.1 Estrutura do projeto
- [ ] 4.1.1 Criar `services/agent/pyproject.toml` com deps: fastapi, uvicorn, pydantic, agno, psycopg, motor, redis, httpx
- [ ] 4.1.2 Criar estrutura de camadas: `app/transport/`, `app/application/`, `app/domain/`, `app/infrastructure/`
- [ ] 4.1.3 Configurar `.python-version` e `uv` ou `poetry` para gerenciamento

### 4.2 Health check
- [ ] 4.2.1 `GET /health` → retorna `HealthResponse` com status de DB, Redis, MinIO
- [ ] 4.2.2 `GET /ready` → verifica conectividade real com dependências
- [ ] 4.2.3 Teste unitário para health endpoint

### 4.3 Stubs de endpoints (retornam 501 ou mock)
- [ ] 4.3.1 `POST /v1/process-document` → stub com resposta mock
- [ ] 4.3.2 `POST /v1/chat` → stub com resposta mock
- [ ] 4.3.3 `POST /v1/summarize-document` → stub com resposta mock
- [ ] 4.3.4 `POST /v1/compare-documents` → stub com resposta mock
- [ ] 4.3.5 Todos os stubs logam request recebido para debug

### 4.4 Injeção de dependência (DI)
- [ ] 4.4.1 Criar container DI (FastAPI `Depends` ou `dependency-injector`)
- [ ] 4.4.2 Registrar: DB connection pool, Redis client, MinIO client, MongoDB client
- [ ] 4.4.3 Provider de config a partir de env vars
- [ ] 4.4.4 Teste de integração: container sobe com deps mock

### 4.5 Config e startup
- [ ] 4.5.1 `Settings` class com Pydantic Settings (lê `.env`)
- [ ] 4.5.2 Lifespan event: conecta DB, Redis, MinIO, MongoDB no startup; fecha no shutdown
- [ ] 4.5.3 Middleware de request ID (`X-Request-ID`)
- [ ] 4.5.4 Middleware de timing (log duração de cada request)

---

## 5. Bootstrap Go/Gin (Serviço Gateway)

### 5.1 Estrutura do projeto
- [ ] 5.1.1 `go mod init` em `services/gateway/`
- [ ] 5.1.2 Estrutura de camadas: `cmd/`, `internal/transport/`, `internal/application/`, `internal/domain/`, `internal/infrastructure/`
- [ ] 5.1.3 Deps: gin, zap (logs), prometheus client, go-redis, retry lib, circuit breaker lib

### 5.2 Health check
- [ ] 5.2.1 `GET /health` → status do gateway + dependências
- [ ] 5.2.2 `GET /ready` → verifica Python agent, Redis, DB
- [ ] 5.2.3 Teste unitário para health handler

### 5.3 HTTP Client para Python Agent
- [ ] 5.3.1 Criar `AgentClient` struct com base URL configurável
- [ ] 5.3.2 Métodos: `ProcessDocument()`, `Chat()`, `Summarize()`, `Compare()`
- [ ] 5.3.3 Timeout configurável por operação (default 30s)
- [ ] 5.3.4 Retry com backoff exponencial (max 3 tentativas)
- [ ] 5.3.5 Teste com httptest server mock

### 5.4 Middlewares base
- [ ] 5.4.1 Middleware de recovery (panic → 500 JSON)
- [ ] 5.4.2 Middleware de request ID (gera ou repassa `X-Request-ID`)
- [ ] 5.4.3 Middleware de logging estruturado (zap, JSON format)
- [ ] 5.4.4 Middleware de CORS (configurável via env)
- [ ] 5.4.5 Middleware de metrics Prometheus (counter de requests, histogram de latência)

### 5.5 Stub de rotas proxy
- [ ] 5.5.1 `POST /v1/process-document` → encaminha para Python agent stub
- [ ] 5.5.2 `POST /v1/chat` → encaminha para Python agent stub
- [ ] 5.5.3 `POST /v1/summarize-document` → encaminha para Python agent stub
- [ ] 5.5.4 `POST /v1/compare-documents` → encaminha para Python agent stub
- [ ] 5.5.5 Tratamento de erro: se Python indisponível → 503 com retry-after

### 5.6 Config e startup
- [ ] 5.6.1 `Config` struct com viper ou env direto
- [ ] 5.6.2 Graceful shutdown (context com timeout)
- [ ] 5.6.3 Porta configurável via `PORT` env var

---

## 6. Observabilidade + Quality Gates

### 6.1 Logs estruturados
- [ ] 6.1.1 Go: zap logger com JSON output, levels (debug/info/warn/error)
- [ ] 6.1.2 Python: structlog ou logging JSON, mesmos levels
- [ ] 6.1.3 Campos padrão em todo log: `request_id`, `service`, `timestamp`, `level`, `message`
- [ ] 6.1.4 Log de startup com versão do serviço e config não-sensível

### 6.2 Métricas Prometheus
- [ ] 6.2.1 Go: `/metrics` endpoint exposto
- [ ] 6.2.2 Métricas: `http_requests_total` (labels: method, path, status), `http_request_duration_seconds`
- [ ] 6.2.3 Python: `/metrics` endpoint via `prometheus-fastapi-instrumentator`
- [ ] 6.2.4 Métricas custom: `agent_call_duration_seconds`, `agent_call_errors_total`
- [ ] 6.2.5 Prometheus no docker-compose para scrape local

### 6.3 Tracing (base)
- [ ] 6.3.1 Go: OTel SDK com trace provider, propagator W3C
- [ ] 6.3.2 Python: OTel SDK com auto-instrumentation FastAPI
- [ ] 6.3.3 Propagação de trace context entre Go → Python via headers
- [ ] 6.3.4 Jaeger no docker-compose para visualização local

### 6.4 CI base (GitHub Actions)
- [ ] 6.4.1 Workflow `ci.yml` com trigger em push/PR para `main`
- [ ] 6.4.2 Job Go: `golangci-lint`, `go test ./...`, `go build`
- [ ] 6.4.3 Job Python: `ruff check`, `ruff format --check`, `pytest`
- [ ] 6.4.4 Job infra: valida `docker-compose.yml` com `docker compose config`
- [ ] 6.4.5 Cache de deps (Go modules, Python venv)

### 6.5 Linting e formatação
- [ ] 6.5.1 Go: `golangci-lint` com config `.golangci.yml`
- [ ] 6.5.2 Python: `ruff` com config `pyproject.toml`
- [ ] 6.5.3 Pre-commit hook opcional (lint + format antes do commit)

### 6.6 Testes smoke end-to-end local
- [ ] 6.6.1 Script `scripts/smoke-test.sh` que sobe infra + serviços
- [ ] 6.6.2 Chama `GET /health` em ambos os serviços e valida 200
- [ ] 6.6.3 Chama stub `POST /v1/chat` e valida resposta mock
- [ ] 6.6.4 Script retorna exit code 0 se tudo passar

---

## Critérios de Conclusão da Fase 0

- [ ] `docker compose --profile infra up` sobe PostgreSQL+pgvector, MongoDB, Redis, MinIO, Prometheus, Jaeger
- [ ] `make migrate` roda todas as migrações sem erro
- [ ] `GET /health` retorna 200 em Go e Python com todas as dependências `true`
- [ ] Stubs de todos os 4 endpoints respondem com mock válido
- [ ] Logs estruturados com `request_id` em ambos os serviços
- [ ] `/metrics` exposto e scrapeável pelo Prometheus
- [ ] Traces visíveis no Jaeger para chamadas Go → Python
- [ ] CI passa em PR (lint + test + build)
- [ ] `scripts/smoke-test.sh` executa com sucesso
- [ ] Documentação em `docs/fase-0-fundacao.md` (PT-BR) com contexto, decisões, e próximos passos
