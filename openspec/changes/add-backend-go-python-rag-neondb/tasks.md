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

---

# Tasks — FASE 2: Resiliência e Escala do Go Gateway

> Escopo: robustez operacional do gateway Go para chamadas ao Python agent, controle de consumo, processamento assíncrono de PDF e notificação de status ao BFF.
> Cada item <= 1-2 dias de trabalho.

## 7. Timeout por operação + política de idempotência

### 7.1 Configuração de timeout por endpoint
- [x] 7.1.1 Adicionar no `Config` timeouts separados para `chat`, `summarize`, `compare`, `process-document` e `health`
- [x] 7.1.2 Definir defaults seguros por operação (ex.: chat 30s, process-document 60s)
- [x] 7.1.3 Atualizar parser de env vars para aceitar durações por operação

### 7.2 Uso de timeout no client Go -> Python
- [x] 7.2.1 Refatorar `python.Client` para suportar timeout por operação
- [x] 7.2.2 Garantir que cada método (`Chat`, `Summarize`, `Compare`, `ProcessDocument`) use seu timeout específico
- [x] 7.2.3 Cobrir em teste unitário timeout correto por operação

### 7.3 Política de idempotência
- [x] 7.3.1 Definir matriz de idempotência por endpoint em `docs/` (quais aceitam retry automático)
- [x] 7.3.2 Bloquear retry automático para `process-document` por padrão
- [x] 7.3.3 Adicionar teste validando ausência de retry em operação não idempotente

## 8. Circuit breaker para dependência Python

### 8.1 Implementação base do circuit breaker
- [x] 8.1.1 Escolher biblioteca de circuit breaker para Go e justificar em doc da feature
- [x] 8.1.2 Implementar breaker por operação upstream no client Python
- [x] 8.1.3 Parametrizar limiar de falhas, janela e cooldown por env

### 8.2 Integração com handlers
- [x] 8.2.1 Mapear estado `open` para resposta HTTP elegante sem chamada remota
- [x] 8.2.2 Padronizar payload de erro para indisponibilidade por breaker aberto
- [x] 8.2.3 Expor estado atual do breaker em endpoint de health/readiness (quando aplicável)

### 8.3 Testes de estado
- [x] 8.3.1 Testar transição `closed -> open` com falhas consecutivas
- [x] 8.3.2 Testar transição `open -> half-open` após cooldown
- [x] 8.3.3 Testar transição `half-open -> closed` em recuperação de upstream

## 9. Retry com backoff exponencial (somente idempotentes)

### 9.1 Política de retry
- [x] 9.1.1 Implementar backoff exponencial com jitter
- [x] 9.1.2 Restringir retry automático a `chat`, `summarize` e `compare`
- [x] 9.1.3 Definir limites: tentativas máximas, timeout total e erros retryable

### 9.2 Observabilidade de retry
- [x] 9.2.1 Instrumentar contador de tentativas por operação
- [x] 9.2.2 Instrumentar contador de falhas finais após esgotar retries
- [x] 9.2.3 Registrar tentativa, atraso e erro em logs estruturados

### 9.3 Testes
- [x] 9.3.1 Validar sucesso após falha transitória em operação idempotente
- [x] 9.3.2 Validar falha final após exceder máximo de tentativas
- [x] 9.3.3 Validar que `process-document` não executa retry automático

## 10. Rate limiting por usuário/projeto

### 10.1 Middleware de limitação
- [x] 10.1.1 Implementar token bucket por chave `user_id + project_id`
- [x] 10.1.2 Implementar fallback por IP quando identificadores não estiverem presentes
- [x] 10.1.3 Expor configuração de taxa e burst por env

### 10.2 Contrato de erro 429
- [x] 10.2.1 Padronizar resposta `429` com código e mensagem de limite excedido
- [x] 10.2.2 Adicionar headers de limite (ex.: remaining/reset) quando aplicável
- [x] 10.2.3 Garantir consistência de resposta entre endpoints

### 10.3 Testes
- [x] 10.3.1 Testar requests abaixo do limite (passam)
- [x] 10.3.2 Testar requests acima do limite (bloqueiam com 429)
- [x] 10.3.3 Testar isolamento entre usuários/projetos distintos

## 11. Fila concorrente de processamento de PDF

### 11.1 Modelo de fila e workers
- [x] 11.1.1 Definir interface de fila para jobs de `process-document`
- [x] 11.1.2 Implementar worker pool com goroutines/channels
- [x] 11.1.3 Parametrizar concorrência e tamanho de buffer por env

### 11.2 Ciclo de vida do job
- [x] 11.2.1 Registrar status `pending` no enfileiramento
- [x] 11.2.2 Atualizar status para `processing` no início da execução
- [x] 11.2.3 Atualizar status para `ready` ou `error` ao finalizar

### 11.3 Integração HTTP
- [x] 11.3.1 Ajustar endpoint de `process-document` para resposta rápida de aceite
- [x] 11.3.2 Garantir que fluxo de chat não dependa do worker de ingestão
- [x] 11.3.3 Cobrir em testes de integração cenário de pico de ingestão

## 12. Webhook de status para BFF

### 12.1 Contrato e segurança
- [x] 12.1.1 Definir contrato final de webhook em `contracts/` (status, ids, timestamp, metadata)
- [x] 12.1.2 Assinar payload com HMAC (secret por env)
- [x] 12.1.3 Incluir header de idempotência no envio

### 12.2 Entrega e confiabilidade
- [x] 12.2.1 Implementar envio de webhook para transições finais (`ready`, `error`)
- [x] 12.2.2 Implementar retry controlado para falhas transitórias no destino
- [x] 12.2.3 Evitar reentrega destrutiva com chave idempotente

### 12.3 Testes
- [x] 12.3.1 Validar assinatura HMAC no payload gerado
- [x] 12.3.2 Validar retries de entrega com destino intermitente
- [x] 12.3.3 Validar deduplicação por idempotência

## 13. Observabilidade de resiliência

### 13.1 Métricas
- [x] 13.1.1 Expor métricas de circuit breaker (estado e transições)
- [x] 13.1.2 Expor métricas de fila (queue depth, tempo de processamento)
- [x] 13.1.3 Expor métricas de rate limiting (requests bloqueadas)
- [x] 13.1.4 Expor métricas de retry (tentativas e falhas finais)
- [x] 13.1.5 Expor métricas de webhook (envios e latência)

### 13.2 Logs estruturados
- [x] 13.2.1 Garantir campos padrão: `request_id`, `project_id`, `user_id`, `operation`
- [x] 13.2.2 Registrar eventos de breaker, retry, enqueue/dequeue e webhook
- [x] 13.2.3 Evitar vazamento de dados sensíveis em logs

## Critérios de Conclusão da Fase 2

- [x] Timeouts por operação ativos e testados
- [x] Circuit breaker ativo em chamadas Go -> Python com transições validadas
- [x] Retry com backoff aplicado somente em operações idempotentes
- [x] Rate limiting por usuário/projeto com resposta `429` padronizada
- [x] Fila concorrente de PDF em produção local com workers estáveis
- [x] Webhook de status (`ready`/`error`) entregue com assinatura e idempotência
- [x] Métricas de resiliência disponíveis em `/metrics`
- [x] Testes unitários e de integração da fase passando
- [ ] Teste de carga básico executado com evidências em documentação
- [x] Documentação da fase em `docs/*fase-2*.md` e `docs/*feature-2-*.md`
