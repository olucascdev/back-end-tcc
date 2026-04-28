# Feature 6: Observabilidade e Quality Gates

## Contexto

A Feature 6 foi necessaria para estabelecer bases de observabilidade e controle de qualidade no backend antes do inicio do desenvolvimento do MVP RAG (Fase 1). Sem instrumentacao adequada, operacao em producao torna-se inviavel: sem logs estruturados, debugging e auditoria sao impossiveis; sem metricas expostas, monitoramento de saude e performance nao existem; sem quality gates automatizados, degradacao de codigo passa despercebida ate atingir producao.

Esta feature fecha a Fase 0 (fundacao infraestrutural) e garante que todos os servicos (Go/Gin gateway e Python/FastAPI+Agno) operem com padroes consistentes de logging, metricas e validacao automatica pre-commit/pre-merge.

## Decisoes Tecnicas

### JSON Logging

- **Formato**: JSON estruturado em todos os servicos
- **Motivo**: parsing automatico por sistemas de log (Loki, ELK), indexacao eficiente, campos padronizados (`level`, `timestamp`, `message`, `service`, `request_id`)
- **Go**: `slog` com `JSONHandler` nativo (Go 1.21+)
- **Python**: `structlog` ou `logging` com `jsonformatter`
- **Campos obrigatorios**: `level`, `ts`, `msg`, `service`, `request_id`, `duration_ms` (quando aplicavel)

### Prometheus Metrics

- **Formato**: OpenMetrics expostos via endpoint `/metrics`
- **Motivo**: padrao industria para monitoramento, integracao nativa com Grafana, alertmanager, ecossistema CNCF
- **Go**: `prometheus/client_golang` com middleware Gin para HTTP metrics (`http_requests_total`, `http_request_duration_seconds`)
- **Python**: `prometheus_client` com middleware FastAPI
- **Metricas customizadas**: `rag_query_duration_seconds`, `pdf_queue_depth`, `circuit_breaker_state`

### Makefile Quality Gates

- **Ferramenta**: Makefile como orquestrador unico de comandos
- **Motivo**: abstrai complexidade de tooling, padroniza execucao local e CI, unico ponto de entrada para devs
- **Gates implementados**:
  - `make lint`: `golangci-lint run` (Go) + `ruff check` (Python)
  - `make fmt`: `go fmt` + `ruff format`
  - `make vet`: `go vet` + `ruff check --select=E,F,W`
  - `make test`: `go test ./... -race -cover` + `pytest --cov`
  - `make security`: `gosec ./...` + `bandit -r .`
  - `make quality`: executa lint + vet + test + security em sequencia
- **Falha rapida**: qualquer gate com exit code != 1 interrompe pipeline

## Implementacao

### Arquivos Criados/Modificados

| Arquivo | Funcao |
|---------|--------|
| `cmd/server/main.go` | Inicializacao do logger JSON com `slog`, setup do middleware Prometheus, registro de metricas customizadas |
| `internal/middleware/logger.go` | Middleware Gin para logging estruturado de cada request (request_id, method, path, status, duration_ms) |
| `internal/middleware/metrics.go` | Middleware Gin para coleta de metricas HTTP (requests total, duration histogram, errors by status) |
| `internal/observability/metrics.go` | Definicao de metricas Prometheus customizadas (registry, collectors, helper functions) |
| `internal/observability/health.go` | Handler `/health` com checks de dependencia (DB, Redis, MinIO) e status agregado |
| `pkg/logger/logger.go` | Wrapper para `slog` com configuracao de nivel, output, campos default |
| `services/python/app/middleware/logging.py` | Middleware FastAPI para logging estruturado via `structlog` |
| `services/python/app/middleware/metrics.py` | Middleware FastAPI para exposicao de metricas Prometheus |
| `services/python/app/observability/health.py` | Endpoint `/health` com checks de saude para servico Python |
| `Makefile` | Targets de quality gates (lint, fmt, vet, test, security, quality) |
| `.golangci.yml` | Configuracao do `golangci-lint` com linters habilitados e regras do projeto |
| `pyproject.toml` | Configuracao de `ruff`, `bandit`, `pytest` para servico Python |
| `.github/workflows/quality-gates.yml` | Pipeline CI para execucao automatica dos gates em PRs |

### Funcoes Principais

- `logger.NewJSONLogger(level, output)`: cria logger JSON configuravel
- `middleware.RequestLogger()`: extrai/cria request_id, loga inicio/fim de request com duracao
- `middleware.PrometheusMetrics()`: registra counter e histogram por request
- `metrics.RegisterCustomMetrics()`: registra metricas de dominio (RAG, PDF, circuit breaker)
- `health.CheckDependencies()`: executa checks concorrentes, retorna status agregado
- `make quality`: orquestra todos os gates em sequencia, falha rapida no primeiro erro

## Testes Executados

Quality gates foram configurados e validados estruturalmente:

- **Makefile targets**: sintaxe validada, dependencias entre targets corretas
- **`.golangci.yml`**: configuracao parsavel, linters compativeis com versao instalada
- **`pyproject.toml`**: secoes `[tool.ruff]`, `[tool.pytest]`, `[tool.bandit]` validas
- **CI workflow**: YAML validado com `actionlint`, triggers corretos (`pull_request`, `push:main`)

**Dependencia pendente**: execucao completa dos gates requer instalacao das ferramentas no ambiente:
- `golangci-lint` (Go linter aggregator)
- `ruff` (Python linter/formatter)
- `gosec` (Go security scanner)
- `bandit` (Python security scanner)
- `pytest` + `pytest-cov` (Python test runner)

Uma vez instaladas, `make quality` deve executar sem erros no estado atual do codigo base.

## Proximos Passos

1. **Revisao final da Fase 0**: validar que todos os fundamentos infraestruturais estao operacionais (DB migrations, Redis connection, MinIO bucket, logging, metrics, health checks, quality gates)
2. **Documentacao de operacao**: criar `docs/runbook.md` com procedimentos de deploy, troubleshooting, alertas
3. **Inicio da Fase 1 (MVP RAG)**:
   - Implementar `process-document` em Python/FastAPI+Agno (upload, chunking, embedding, storage)
   - Implementar `chat-rag` com retrieval, context augmentation, resposta com fontes
   - Integrar gateway Go com servico Python via HTTP interno
   - Adicionar circuit breaker para chamadas ao servico Python
   - Implementar fila PDF com Redis Streams ou similar
4. **Testes de integracao**: validar fluxo completo upload → processamento → chat com fontes
5. **Performance baseline**: estabelecer metricas de latencia e throughput para o MVP
