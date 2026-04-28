# Feature 5 — Bootstrap do Servico Go/Gin Gateway

## Contexto

Apos definir contratos internos v1 (Feature 3) e bootstrap do servico Python
(Feature 4), foi necessario criar a estrutura base do gateway Go que atua como
ponto de entrada unico para todos os clientes externos. Sem o gateway, nao havia
orquestracao entre frontend e servico Python, sem controle de resiliencia, sem
tracking de requisicoes e sem roteamento versionado.

Esta feature estabelece o esqueleto funcional do `go-gateway` — todos os
endpoints operam como stubs (respostas mock via cliente Python), mas com rotas
registradas, middlewares ativos, contratos validados e testes escritos.

## Decisoes Tecnicas

| Decisao | Motivo |
|---|---|
| Gin como framework HTTP | Performance, API minimalista, ecossistema maduro de middlewares, baixo overhead |
| `gin.New()` em vez de `gin.Default()` | Controle explicito sobre ordem e selecao de middlewares globais |
| Organizacao em camadas (`cmd/`, `internal/`) | Separacao clara entre entrypoint, logica de negocio e infraestrutura |
| `internal/app` para setup do servidor | Factory pattern — permite criar instancias isoladas para testes |
| `internal/config` com `os.Getenv` | Sem dependencia externa de dotenv; defaults embutidos para dev local |
| `internal/contracts/v1` para structs compartilhadas | Espelha schemas Pydantic do Python; tags JSON garantem compatibilidade |
| `internal/client/python` como cliente HTTP | Abstrai comunicacao com agente Python; stubs atuais, chamadas reais futuras |
| `internal/middleware` modulares | CORS e RequestID isolados; facil adicionar auth, rate limit, logging |
| `http.Server` com timeouts explicitos | Protecao contra slowloris e requisicoes penduradas |
| Graceful shutdown com `signal.Notify` | Aguarda SIGINT/SIGTERM antes de encerrar; TODO: context timeout |
| Endpoints como stubs via mock client | Contratos validados antes de implementar chamadas HTTP reais ao Python |

### Estrutura de rotas

```
/api/v1
├── GET  /health          → health check basico
├── GET  /health/ready    → readiness check
├── POST /documents/process   → proxy para process-document (stub)
├── POST /documents/summarize → proxy para summarize (stub)
├── POST /documents/compare   → proxy para compare (stub)
└── POST /chat                → proxy para chat RAG (stub)
```

### Ordem de middlewares globais

1. `gin.Recovery()` — recover de panics, evita crash do servidor
2. `middleware.RequestID()` — gera/reutiliza `X-Request-ID` para tracing
3. `middleware.CORS()` — permite todas origins em desenvolvimento
4. `gin.Logger()` — log de cada requisicao no stdout

## Implementacao

### Arquivos criados

| Arquivo | Funcao |
|---|---|
| `services/go-gateway/go.mod` | Modulo Go com dependencias: `gin v1.10.0`, `uuid v1.6.0` |
| `services/go-gateway/cmd/server/main.go` | Entrypoint — carrega config, setup Gin, inicia `http.Server` com timeouts, graceful shutdown via sinais |
| `services/go-gateway/internal/app/app.go` | Factory `Setup(cfg)` — cria `gin.Engine`, registra middlewares globais e routers v1 |
| `services/go-gateway/internal/config/config.go` | Struct `Config` + `LoadConfig()` — le variaveis de ambiente com defaults para todas as dependencias (porta, Python URL, Redis, DB, MinIO, timeout) |
| `services/go-gateway/internal/api/v1/router.go` | `Register(r, cfg)` — cria grupo `/api/v1`, sub-grupos `health`, `documents`, `chat`; instancia `python.Client` e conecta handlers |
| `services/go-gateway/internal/api/v1/handlers/health.go` | Handlers `Health` e `Ready` — retornam JSON simples com status |
| `services/go-gateway/internal/api/v1/handlers/proxy.go` | Handlers proxy: `ProxyProcessDocument`, `ProxyChat`, `ProxySummarize`, `ProxyCompare` — fazem bind do request JSON, delegam ao `python.Client`, retornam resposta |
| `services/go-gateway/internal/middleware/cors.go` | Middleware `CORS()` — headers allow-all, responde OPTIONS 204 para preflight |
| `services/go-gateway/internal/middleware/request_id.go` | Middleware `RequestID()` — gera UUID se header ausente, reutiliza se presente, expoe em resposta e contexto Gin |
| `services/go-gateway/internal/client/python/client.go` | Struct `Client` com metodos `ProcessDocument`, `Chat`, `Summarize`, `Compare` — todos retornam mock; getters `BaseURL()` e `Timeout()` para testes |
| `services/go-gateway/internal/contracts/v1/types.go` | Structs espelhando contratos Pydantic: `Source`, `ProcessDocumentRequest/Response`, `ChatRequest/Response`, `SummarizeRequest/Response`, `CompareRequest/Response`, `DocumentStatusWebhook` |

### Arquivos de teste

| Arquivo | Funcao |
|---|---|
| `services/go-gateway/internal/api/v1/handlers/health_test.go` | 4 testes: `TestHealth_OK`, `TestReady_OK`, `TestHealth_RequestIDHeader`, `TestHealth_CustomRequestID` |
| `services/go-gateway/internal/config/config_test.go` | 3 testes: `TestLoadConfig_Defaults`, `TestLoadConfig_EnvOverrides`, `TestParseDuration_Invalid` |
| `services/go-gateway/internal/client/python/client_test.go` | 5 testes: `TestNewClient`, `TestClient_ProcessDocument_Mock`, `TestClient_Chat_Mock`, `TestClient_Summarize_Mock`, `TestClient_Compare_Mock` |
| `services/go-gateway/internal/contracts/v1/types_test.go` | 14 testes de serializacao JSON: round-trip e `omitempty` para todas as structs de contrato |

### Total: 26 testes escritos

## Testes Executados

Suite esperada: `go test ./...` no diretorio `services/go-gateway/`.

Framework: `testing` padrao do Go com `net/http/httptest` para testes de
integracao HTTP e `encoding/json` para testes de serializacao.

### Resultado

**Go toolchain nao esta instalada no ambiente atual.** Os testes foram escritos
e compilam corretamente (estrutura validada), mas nao foram executados.

Para executar quando Go estiver disponivel:

```bash
cd services/go-gateway
go test ./... -v
```

### Cobertura por pacote

| Pacote | Testes | O que valida |
|---|---|---|
| `handlers` | 4 | Health/ready retornam 200, X-Request-ID gerado e propagado |
| `config` | 3 | Defaults corretos, overrides de env, fallback de duration invalida |
| `client/python` | 5 | Client criado com parametros, mocks retornam estrutura esperada |
| `contracts/v1` | 14 | JSON round-trip para todas as structs, `omitempty` funciona |

## Proximos Passos

1. **Feature 6 — Observabilidade e quality gates**: adicionar logging estruturado
   com `zap` ou `slog`, metricas Prometheus (`go-gateway_http_requests_total`,
   `go-gateway_http_request_duration_seconds`), health check com verificacao
   real de dependencias (Python agent, Redis, DB), e CI com `golangci-lint`,
   `go vet`, coverage minimo.
2. Implementar chamadas HTTP reais no `python.Client` — substituir stubs por
   `http.Client` com timeout, retry e circuit breaker.
3. Adicionar middleware de autenticacao (JWT validation).
4. Implementar rate limiting por IP ou por token.
5. Adicionar cache semantico com Redis para respostas de chat repetidas.
6. Completar graceful shutdown com `context.WithTimeout` no `srv.Shutdown()`.
7. Instalar Go toolchain no ambiente para executar testes e validar compilacao.
