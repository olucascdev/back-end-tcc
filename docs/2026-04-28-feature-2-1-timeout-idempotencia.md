# Feature 2.1 — Timeout por Operação + Política de Idempotência

**Data:** 2026-04-28
**Status:** Implementado

## Contexto

O gateway Go originalmente utilizava um único `RequestTimeout` (default 30s) para todas as operações com o agente Python. Isso é problemático porque:

- **Processamento de documentos** pode levar mais tempo (geração de chunks + embeddings) — 30s é insuficiente.
- **Health checks** devem ser rápidos — 30s é excessivo e mascara problemas de conectividade.
- **Chat, summarize e compare** têm perfis de latência diferentes entre si.

Sem timeout por operação, ou o gateway corta requisições legítimas (falso timeout) ou mantém conexões abertas desnecessariamente (desperdício de recursos).

## Decisões Técnicas

### Mapa de timeouts por operação

Em vez de múltiplos campos no `Client` ou múltiplos `http.Client` instances, optou-se por um `map[string]time.Duration` no `Client`. Cada método (`Chat`, `Summarize`, `Compare`, `ProcessDocument`) passa seu `opName` para `doRequest`, que consulta o mapa e cria um `context.WithTimeout` com o deadline correto.

**Vantagens:**
- Único `http.Client` compartilhado (connection pooling preservado).
- Controle granular via `context.WithTimeout` — cancelamento propagado automaticamente.
- Fácil adicionar novas operações ao mapa.

### Backward compat com `REQUEST_TIMEOUT`

Quando nenhuma env var específica (`TIMEOUT_CHAT`, `TIMEOUT_SUMMARIZE`, etc.) está definida, o valor de `REQUEST_TIMEOUT` é usado como fallback global. Se `REQUEST_TIMEOUT` também não estiver definido, cada operação usa seu default intrínseco (30s para chat/summarize/compare, 60s para process-document, 5s para health).

### `http.Client.Timeout` alto

O `http.Client.Timeout` foi elevado para 5 minutos. O controle real de timeout é feito via `context.WithTimeout` em cada operação. Isso evita que o timeout do client interfira com o deadline do contexto.

## Matriz de Idempotência

| Operação            | Idempotente? | Retry automático? | Justificativa                                      |
|---------------------|-------------|-------------------|----------------------------------------------------|
| `chat`              | Sim         | Seguro            | Consulta RAG — sem efeito colateral                |
| `summarize`         | Sim         | Seguro            | Gera resumo — sem efeito colateral                 |
| `compare`           | Sim         | Seguro            | Compara documentos — sem efeito colateral          |
| `process-document`  | **Não**     | **Não**           | Cria chunks e embeddings no banco — side effects   |
| `health`            | Sim         | Desnecessário     | Apenas verifica status — sem retry automático      |

**Regra:** operações não-idempotentes (`process-document`) não devem ter retry automático no gateway. Operações idempotentes poderão ter retry quando o circuit breaker for implementado (Feature 2.2).

## Implementação

### Arquivos alterados

#### `internal/config/config.go`
- Removido campo `RequestTimeout time.Duration`.
- Adicionados campos: `TimeoutChat`, `TimeoutSummarize`, `TimeoutCompare`, `TimeoutProcessDocument`, `TimeoutHealth`.
- Adicionada função `parseDurationWithFallback` para lógica de fallback com `REQUEST_TIMEOUT`.
- Env vars: `TIMEOUT_CHAT`, `TIMEOUT_SUMMARIZE`, `TIMEOUT_COMPARE`, `TIMEOUT_PROCESS_DOCUMENT`, `TIMEOUT_HEALTH`.

#### `internal/config/config_test.go`
- `TestLoadConfig_DefaultTimeoutsPerOperation` — valida defaults por operação.
- `TestLoadConfig_PerOperationTimeoutOverrides` — valida override por env var específica.
- `TestLoadConfig_GlobalTimeoutFallback` — valida fallback de `REQUEST_TIMEOUT`.
- `TestLoadConfig_SpecificOverridesGlobalFallback` — valida que específico precedence sobre fallback.
- `TestParseDurationWithFallback_InvalidSpecific` — valida fallback quando valor específico é inválido.
- Refatorado `TestLoadConfig_Defaults` e `TestLoadConfig_EnvOverrides` para usar helper `clearEnvVars`.

#### `internal/client/python/client.go`
- `Client` struct: campo `timeout time.Duration` → `timeouts map[string]time.Duration`.
- `NewClient` assinatura: `(baseURL string, timeout time.Duration)` → `(baseURL string, timeouts map[string]time.Duration)`.
- `doRequest` agora cria `context.WithTimeout(ctx, timeout)` usando timeout da operação.
- Adicionado método `GetTimeout(opName string)` para testes.
- Removido método `Timeout()` (substituído por `GetTimeout`).
- `http.Client.Timeout` elevado para 5min (controle real via contexto).

#### `internal/client/python/client_test.go`
- Todos os testes existentes atualizados para usar `testTimeouts()` helper.
- `TestClient_TimeoutPerOperation` — valida que operações diferentes usam timeouts diferentes.
- `TestClient_DefaultTimeoutWhenMissing` — valida fallback 30s quando operação não está no mapa.
- `TestClient_Timeout` atualizado para usar mapa com timeout específico de 100ms.

#### `internal/api/v1/router.go`
- Constrói mapa de timeouts a partir dos campos do `Config`.
- Passa mapa para `python.NewClient`.

## Testes Executados

| Teste                                           | Resultado  |
|-------------------------------------------------|------------|
| `TestLoadConfig_Defaults`                       | ✅ Pass    |
| `TestLoadConfig_DefaultTimeoutsPerOperation`    | ✅ Pass    |
| `TestLoadConfig_EnvOverrides`                   | ✅ Pass    |
| `TestLoadConfig_PerOperationTimeoutOverrides`   | ✅ Pass    |
| `TestLoadConfig_GlobalTimeoutFallback`          | ✅ Pass    |
| `TestLoadConfig_SpecificOverridesGlobalFallback`| ✅ Pass    |
| `TestParseDuration_Invalid`                     | ✅ Pass    |
| `TestParseDurationWithFallback_InvalidSpecific` | ✅ Pass    |
| `TestNewClient`                                 | ✅ Pass    |
| `TestClient_ProcessDocument_Success`            | ✅ Pass    |
| `TestClient_Chat_Success`                       | ✅ Pass    |
| `TestClient_Summarize_Success`                  | ✅ Pass    |
| `TestClient_Compare_Success`                    | ✅ Pass    |
| `TestClient_ProcessDocument_5xx_Error`          | ✅ Pass    |
| `TestClient_Chat_4xx_Error`                     | ✅ Pass    |
| `TestClient_Timeout`                            | ✅ Pass    |
| `TestClient_ConnectionError`                    | ✅ Pass    |
| `TestClient_RequestID_Propagated`               | ✅ Pass    |
| `TestClient_TimeoutPerOperation`                | ✅ Pass    |
| `TestClient_DefaultTimeoutWhenMissing`          | ✅ Pass    |

## Próximos Passos

- **Feature 2.2**: Circuit breaker para operações idempotentes (chat, summarize, compare).
- **Feature 2.3**: Retry com backoff exponencial para operações idempotentes.
- **Feature 2.4**: Cache semântico com Redis para respostas de chat.
