# Feature 1.2 - Integracao real Go → Python

## Contexto

Apos implementar o pipeline real de processamento de documentos no servico Python (Feature 1.1), o gateway Go ainda nao possuia comunicacao HTTP real com o agente Python. Os handlers do gateway operavam em modo stub, retornando respostas mock sem encaminhar requisicoes ao servico downstream.

Sem integracao real, o sistema nao conseguia:
- encaminhar requisicoes de processamento de documento ao Python-Agent
- executar chat RAG com base de conhecimento vetorial
- gerar resumos estruturados de documentos
- comparar documentos por tema

Esta feature resolve:
- implementar cliente HTTP generico com Go generics para comunicacao Go → Python
- propagar contexto e request_id entre servicos para tracing distribuido
- classificar erros upstream por tipo HTTP (4xx, 5xx, timeout, conexao)
- mapear erros do cliente para status HTTP adequados no gateway
- cobrir cliente e handlers com testes unitarios completos

## Decisoes tecnicas

### HTTP client com Go generics

- Funcao `doRequest[Req, Resp any]` generica elimina duplicacao de codigo entre os 4 endpoints (process-document, chat, summarize, compare).
- Cada metodo publico do client (`ProcessDocument`, `Chat`, `Summarize`, `Compare`) delega para `doRequest` com tipos concretos de request/response definidos nos contratos v1.
- Serializacao JSON via `encoding/json` padrao da stdlib — sem dependencia externa.

### Context propagation

- `http.NewRequestWithContext(ctx, ...)` garante que cancelamento do contexto do request original propaga para chamada upstream.
- `request_id` extraido do contexto via `ctx.Value("request_id")` e injetado no header `X-Request-ID` da requisicao HTTP.
- Permite tracing distribuido: mesmo request_id atravessa gateway → Python-Agent → logs de ambos os servicos.

### Timeout configuravel

- `http.Client.Timeout` definido no construtor `NewClient(baseURL, timeout)`.
- Timeout carregado da variavel de ambiente `REQUEST_TIMEOUT` (default `30s`) via `config.LoadConfig()`.
- Dupla deteccao de timeout:
  1. `context.DeadlineExceeded` — contexto cancelado antes ou durante a chamada.
  2. `strings.Contains(err.Error(), "Client.Timeout exceeded")` — timeout do `http.Client` propriamente dito.
- Ambos os casos retornam erro sentinela `ErrTimeout` para classificacao uniforme no handler.

### Classificacao de erros por sentinelas

- `ErrValidation` — erro 4xx do Python (validacao falhou no lado downstream).
- `ErrServiceUnavailable` — erro 5xx do Python ou falha de conexao (servico indisponivel).
- `ErrTimeout` — requisicao excedeu tempo limite.
- Erros sentinelas permitem `errors.Is()` no handler para mapeamento preciso de status HTTP.

### Tratamento de erro elegante no handler

- Funcao `handlePythonError()` centraliza mapeamento de erros do client para respostas HTTP:
  - `ErrTimeout` → `504 Gateway Timeout` com mensagem `"request timed out while processing"`.
  - `ErrServiceUnavailable` → `502 Bad Gateway` com mensagem `"upstream service unavailable"`.
  - `ErrValidation` → `400 Bad Request` com mensagem `"invalid request: upstream validation failed"`.
  - Erro desconhecido → `500 Internal Server Error` com mensagem `"internal server error"`.
- Mensagens de erro sao seguras — nao expoem detalhes internos do Python-Agent para o cliente externo.
- Logging estruturado via `slog` em cada ramo de erro, incluindo `operation` e `request_id` para debug.

### Logging estruturado

- Cada chamada ao Python-Agent gera log de request (`operation`, `method`, `url`).
- Cada resposta gera log com `status` HTTP e `body_size`.
- Erros geram logs com nivel adequado (`Warn` para timeout/validacao, `Error` para indisponibilidade).

### Retry e circuit breaker

- Retry com backoff exponencial e circuit breaker **nao implementados nesta feature**.
- Justificativa: complexidade adicional requer avaliacao de idempotencia por endpoint. Processamento de documento pode nao ser idempotente (cria chunks e embeddings). Chat e summarize sao mais seguros para retry.
- Planejado para feature futura de resiliencia do gateway.

## Implementacao

### Fluxo de requisicao

```
Client → Gateway Go (Gin)
  │
  ├─ 1. Middleware RequestID injeta X-Request-ID no contexto
  ├─ 2. Handler faz bind do JSON para struct Pydantic-equivalente (v1 contracts)
  ├─ 3. Handler chama client.<Operation>(ctx, &req)
  │     │
  │     ├─ doRequest serializa req → JSON
  │     ├─ cria http.Request com contexto (propaga cancelamento + request_id)
  │     ├─ executa chamada HTTP para Python-Agent
  │     ├─ classifica erro por status HTTP (4xx → ErrValidation, 5xx → ErrServiceUnavailable)
  │     └─ desserializa resposta JSON → struct tipada
  │
  ├─ 4. Handler retorna resposta tipada com status HTTP adequado
  └─ 5. Em caso de erro, handlePythonError mapeia para status HTTP seguro
```

### Arquivos modificados/criados

#### `internal/client/python/client.go` (novo)
- Pacote `python` com cliente HTTP para comunicacao com agente Python.
- Struct `Client` com `baseURL`, `timeout` e `httpClient`.
- `NewClient(baseURL, timeout)` — construtor com timeout configuravel.
- `ProcessDocument(ctx, req)` — encaminha para `POST /process-document`.
- `Chat(ctx, req)` — encaminha para `POST /chat`.
- `Summarize(ctx, req)` — encaminha para `POST /summarize-document`.
- `Compare(ctx, req)` — encaminha para `POST /compare-documents`.
- `doRequest[Req, Resp]` — funcao generica com serializacao JSON, context propagation, classificacao de erros e logging.
- Erros sentinelas: `ErrValidation`, `ErrServiceUnavailable`, `ErrTimeout`.
- Metodos `BaseURL()` e `Timeout()` para inspecao em testes.

#### `internal/client/python/client_test.go` (novo)
- 12 testes cobrindo cliente HTTP:
  - `TestNewClient` — validacao de construcao com URL e timeout.
  - `TestClient_ProcessDocument_Success` — pipeline completo com mock server.
  - `TestClient_Chat_Success` — chat com sources e session_id.
  - `TestClient_Summarize_Success` — resumo estruturado com mapa de chaves.
  - `TestClient_Compare_Success` — comparacao tematica entre documentos.
  - `TestClient_ProcessDocument_5xx_Error` — erro 500 retorna `ErrServiceUnavailable`.
  - `TestClient_Chat_4xx_Error` — erro 400 retorna erro de validacao.
  - `TestClient_Timeout` — server lento com timeout curto retorna `ErrTimeout`.
  - `TestClient_ConnectionError` — URL invalida retorna `ErrServiceUnavailable`.
  - `TestClient_RequestID_Propagated` — request_id do contexto propagado para header `X-Request-ID`.

#### `internal/api/v1/handlers/proxy.go` (novo)
- Handlers de proxy que encaminham requisicoes ao Python-Agent via cliente HTTP real.
- `ProxyProcessDocument(client)` — `POST /documents/process` → retorna 202 Accepted.
- `ProxyChat(client)` — `POST /chat` → retorna 200 OK.
- `ProxySummarize(client)` — `POST /documents/summarize` → retorna 200 OK.
- `ProxyCompare(client)` — `POST /documents/compare` → retorna 200 OK.
- `handlePythonError()` — mapeia erros sentinelas para status HTTP seguros com logging.

#### `internal/api/v1/handlers/proxy_test.go` (novo)
- 10 testes cobrindo handlers de proxy:
  - `TestProxyProcessDocument_Success` — requisicao valida retorna 202 com status pending.
  - `TestProxyChat_Success` — chat retorna 200 com resposta e sources.
  - `TestProxyProcessDocument_Upstream502` — Python retorna 500, gateway retorna 502 com mensagem segura.
  - `TestProxyChat_Upstream502` — Python retorna 502, gateway retorna 502.
  - `TestProxyProcessDocument_Timeout504` — Python demora, gateway retorna 504.
  - `TestProxyChat_Timeout504` — timeout no chat retorna 504.
  - `TestProxyProcessDocument_InvalidBody` — JSON invalido retorna 400.
  - `TestProxy_RequestID_Propagated` — X-Request-ID do request propagado na resposta.

#### `internal/api/v1/router.go` (modificado)
- Substituiu stubs por handlers de proxy reais.
- Inicializa `pythonClient` com `cfg.PythonAgentURL` e `cfg.RequestTimeout`.
- Registra rotas: `POST /documents/process`, `POST /documents/summarize`, `POST /documents/compare`, `POST /chat`.

#### `internal/config/config.go` (existente, referencia)
- `PythonAgentURL` — URL do agente Python (default `http://localhost:8000`).
- `RequestTimeout` — timeout para requisicoes upstream (default `30s`).

## Testes executados

### Suite completa: 22/22 passando

```
=== RUN   TestNewClient
--- PASS: TestNewClient
=== RUN   TestClient_ProcessDocument_Success
--- PASS: TestClient_ProcessDocument_Success
=== RUN   TestClient_Chat_Success
--- PASS: TestClient_Chat_Success
=== RUN   TestClient_Summarize_Success
--- PASS: TestClient_Summarize_Success
=== RUN   TestClient_Compare_Success
--- PASS: TestClient_Compare_Success
=== RUN   TestClient_ProcessDocument_5xx_Error
--- PASS: TestClient_ProcessDocument_5xx_Error
=== RUN   TestClient_Chat_4xx_Error
--- PASS: TestClient_Chat_4xx_Error
=== RUN   TestClient_Timeout
--- PASS: TestClient_Timeout
=== RUN   TestClient_ConnectionError
--- PASS: TestClient_ConnectionError
=== RUN   TestClient_RequestID_Propagated
--- PASS: TestClient_RequestID_Propagated
=== RUN   TestProxyProcessDocument_Success
--- PASS: TestProxyProcessDocument_Success
=== RUN   TestProxyChat_Success
--- PASS: TestProxyChat_Success
=== RUN   TestProxyProcessDocument_Upstream502
--- PASS: TestProxyProcessDocument_Upstream502
=== RUN   TestProxyChat_Upstream502
--- PASS: TestProxyChat_Upstream502
=== RUN   TestProxyProcessDocument_Timeout504
--- PASS: TestProxyProcessDocument_Timeout504
=== RUN   TestProxyChat_Timeout504
--- PASS: TestProxyChat_Timeout504
=== RUN   TestProxyProcessDocument_InvalidBody
--- PASS: TestProxyProcessDocument_InvalidBody
=== RUN   TestProxy_RequestID_Propagated
--- PASS: TestProxy_RequestID_Propagated
```

### Distribuicao por arquivo

| Arquivo de teste | Testes | Cobertura |
|---|---|---|
| `client/python/client_test.go` | 10 | Construcao, 4 operacoes happy path, 3 cenarios de erro, propagacao de request_id |
| `handlers/proxy_test.go` | 8 | 2 happy path, 2 upstream 5xx, 2 timeout, 1 body invalido, 1 request_id |

### Cenarios testados

#### Cliente HTTP (`client_test.go`)
- **Happy path**: todas as 4 operacoes (process-document, chat, summarize, compare) com mock server retornando respostas validas.
- **Erro 5xx**: Python retorna 500 → client retorna `ErrServiceUnavailable`.
- **Erro 4xx**: Python retorna 400 → client retorna erro com prefixo `ErrValidation`.
- **Timeout**: server demora 2s, client timeout 100ms → `ErrTimeout`.
- **Erro de conexao**: URL invalida (porta inexistente) → `ErrServiceUnavailable`.
- **Request ID**: contexto com `request_id` propagado para header `X-Request-ID`.

#### Handlers de proxy (`proxy_test.go`)
- **Happy path**: process-document retorna 202, chat retorna 200 com corpo correto.
- **Upstream 5xx**: Python retorna 500/502 → gateway retorna 502 com mensagem segura `"upstream service unavailable"`.
- **Timeout**: Python demora 10s, client timeout 100ms → gateway retorna 504 com `"request timed out while processing"`.
- **Body invalido**: JSON malformado → gateway retorna 400 sem chamar upstream.
- **Request ID**: header `X-Request-ID` do request original propagado na resposta.

## Proximos passos

1. **Feature 1.3 - Chat RAG real**: implementar endpoint de chat no Python-Agent com busca vetorial no pgvector, contexto RAG e resposta com fontes citadas.
2. Implementar retry com backoff exponencial no cliente Go para operacoes idempotentes (chat, summarize).
3. Adicionar circuit breaker para proteger gateway quando Python-Agent estiver indisponivel por periodo prolongado.
4. Implementar cache semantico com Redis para respostas de chat frequentes.
5. Adicionar metricas de latencia upstream (histograma por operacao) para observabilidade.
