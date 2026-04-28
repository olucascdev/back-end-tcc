# Feature 4 — Bootstrap do Servico Python/FastAPI

## Contexto

Apos definir contratos internos v1 (Feature 3), foi necessario criar a estrutura
base do servico Python que implementara os endpoints reais de processamento de
documentos, chat RAG, resumo e comparacao. Sem o bootstrap, nao havia aplicacao
FastAPI rodando, sem routers, sem configuracao de ambiente e sem testes de
integracao da API.

Esta feature estabelece o esqueleto funcional do `python-agent` — todos os
endpoints operam como stubs (respostas mock), mas com contratos validados,
rotas registradas e testes passando.

## Decisoes Tecnicas

| Decisao | Motivo |
|---|---|
| FastAPI como framework | Async nativo, validacao Pydantic integrada, geracao automatica de OpenAPI |
| Factory pattern (`create_app`) | Permite criar instancias isoladas para testes e producao |
| `lifespan` context manager | Substitui deprecated `@app.on_event("startup"/"shutdown")` no Python 3.12+ |
| Routers modulares por dominio | Separacao clara: `health`, `documents`, `chat`, `summarize`, `compare` |
| `pydantic_settings.BaseSettings` | Carrega `.env` automaticamente com valores default para desenvolvimento |
| Dependency injection via `Depends()` | Padrao FastAPI para fornecer `Settings` e futuras conexoes (DB, Redis) |
| CORS `allow_origins=["*"]` | Configuracao temporaria para desenvolvimento; restringir em producao |
| Global exception handler | Retorna JSON padronizado `{error, detail}` em vez de stack trace HTML |
| Endpoints como stubs | Contratos validados antes de implementar logica real de RAG/LLM |

### Estrutura de routers

```
/api/v1
├── GET  /health          → health check basico
├── GET  /ready           → readiness check com dependencias
├── POST /documents/process-document → aceita documento para processamento
├── POST /chat            → chat RAG com contexto
├── POST /summarize/summarize-document → resumo estruturado
└── POST /compare/compare-documents   → comparacao tematica
```

## Implementacao

### Arquivos criados

| Arquivo | Funcao |
|---|---|
| `services/python-agent/app/__init__.py` | Marca pacote Python |
| `services/python-agent/app/main.py` | Ponto de entrada — factory `create_app()`, middleware CORS, router v1, exception handler global |
| `services/python-agent/app/core/__init__.py` | Marca pacote core |
| `services/python-agent/app/core/config.py` | Classe `Settings` com `pydantic_settings` — carrega `.env` com defaults |
| `services/python-agent/app/core/deps.py` | Dependencias injetaveis: `get_settings()`, `get_db()` (placeholder) |
| `services/python-agent/app/api/__init__.py` | Marca pacote api |
| `services/python-agent/app/api/v1/__init__.py` | Marca pacote v1 |
| `services/python-agent/app/api/v1/router.py` | Router principal v1 — agrega todos os sub-routers |
| `services/python-agent/app/api/v1/endpoints/__init__.py` | Marca pacote endpoints |
| `services/python-agent/app/api/v1/endpoints/health.py` | Endpoints `/health` e `/ready` |
| `services/python-agent/app/api/v1/endpoints/documents.py` | Endpoint `POST /process-document` (stub) |
| `services/python-agent/app/api/v1/endpoints/chat.py` | Endpoint `POST /chat` (stub) |
| `services/python-agent/app/api/v1/endpoints/summarize.py` | Endpoint `POST /summarize-document` (stub) |
| `services/python-agent/app/api/v1/endpoints/compare.py` | Endpoint `POST /compare-documents` (stub) |
| `services/python-agent/tests/__init__.py` | Marca pacote tests |
| `services/python-agent/tests/test_api_v1.py` | 6 testes de integracao da API v1 |

### Arquivos pre-existentes reutilizados

| Arquivo | Uso |
|---|---|
| `app/schemas/contracts_v1.py` | Modelos Pydantic usados como `request` e `response_model` em todos os endpoints |

## Testes Executados

Suite: `pytest services/python-agent/tests/test_api_v1.py`

Framework: pytest com `fastapi.testclient.TestClient`.

### Resultado

```
6 passed
```

### Detalhamento por teste

| Teste | Endpoint | Verificacao |
|---|---|---|
| `test_health_returns_ok` | `GET /api/v1/health` | Status 200, body `{"status": "ok"}` |
| `test_ready_returns_ready` | `GET /api/v1/ready` | Status 200, `status=ready`, `checks.database=ok` |
| `test_process_document_returns_processing` | `POST /api/v1/documents/process-document` | Status 200, `status=processing`, `document_id` presente |
| `test_chat_returns_answer` | `POST /api/v1/chat` | Status 200, `answer` presente, `sources=[]`, `session_id` echo |
| `test_summarize_returns_structured_summary` | `POST /api/v1/summarize/summarize-document` | Status 200, `summary` com chaves `objective`, `methodology`, `results`, `conclusion` |
| `test_compare_returns_comparison` | `POST /api/v1/compare/compare-documents` | Status 200, `comparison.theme` igual ao enviado, `sources=[]` |

Todos os 6 testes passaram. Endpoints operam como stubs — retornam dados mock
com estrutura compativel com os contratos Pydantic definidos na Feature 3.

## Proximos Passos

1. **Feature 5 — Bootstrap do gateway Go/Gin**: criar estrutura do servico Go com
   routers, middleware de resiliencia (timeout, retry), e roteamento para os
   endpoints Python implementados nesta feature.
2. Implementar logica real de `process-document`: ingestao de PDF, chunking,
   geracao de embeddings e persistencia em pgvector.
3. Conectar `get_db()` a engine async real (SQLAlchemy + asyncpg).
4. Substituir stubs de `chat`, `summarize` e `compare` por chamadas ao LLM via
   Agno com retrieval vetorial.
5. Restringir CORS para origens conhecidas em producao.
6. Adicionar middleware de logging estruturado com `request_id`, `project_id`,
   `user_id`.
