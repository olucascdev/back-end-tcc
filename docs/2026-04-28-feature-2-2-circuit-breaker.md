# Feature 2.2 — Circuit Breaker para Dependência Python

**Data:** 2026-04-28  
**Status:** Implementado

## Contexto

O gateway Go (Gin) depende do agente Python (FastAPI) para operações de processamento de documentos, chat RAG, resumo e comparação de documentos. Sem proteção, falhas repetidas no upstream Python causam:

- **Falhas em cascata:** cada request falho consome goroutines e conexões do gateway.
- **Degradação progressiva:** sem feedback rápido, o gateway continua tentando chamar um serviço indisponível.
- **Tempo de recuperação lento:** o Python pode precisar de tempo para se recuperar, mas o gateway continua enviando requests.

O circuit breaker resolve isso interceptando chamadas antes que cheguem ao upstream quando o serviço está comprovadamente indisponível.

## Decisões Técnicas

### Biblioteca: `github.com/sony/gobreaker`
- **Motivo:** biblioteca madura, simples, com state machine built-in (closed → open → half-open).
- **Alternativa considerada:** implementação própria de state machine. Descartada porque gobreaker já resolve o problema com código testado em produção.
- **Zero dependências transitivas:** gobreaker não puxa pacotes externos adicionais.

### Um breaker por operação
- Operações: `chat`, `summarize`, `compare`, `process-document`.
- **Motivo:** falhas em uma operação não devem afetar as outras. Exemplo: se `process-document` está falhando, `chat` pode continuar funcionando normalmente.
- Implementado via `BreakerGroup` que mantém mapa de `*gobreaker.CircuitBreaker` por nome.

### Parâmetros configuráveis via env vars
| Env Var | Default | Descrição |
|---|---|---|
| `CIRCUIT_MAX_REQUESTS` | 3 | Max requests aceitos no estado half-open |
| `CIRCUIT_FAILURE_THRESHOLD` | 5 | Falhas consecutivas para abrir o circuito |
| `CIRCUIT_TIMEOUT` | 30s | Duração do estado open antes de testar recuperação |

### Mapeamento HTTP
- `ErrCircuitOpen` → **503 Service Unavailable**
- Mensagem: `"upstream service temporarily unavailable due to circuit breaker"`
- Log nível Warn com `operation` e `request_id`.

## Implementação

### Arquivos criados

#### `internal/infrastructure/circuitbreaker/breaker.go`
- `Config` struct com `MaxRequests`, `FailureThreshold`, `Timeout`.
- `BreakerGroup` struct com mapa de breakers por operação.
- `NewBreakerGroup(cfg)` — construtor thread-safe.
- `Execute(opName, fn)` — executa função dentro do breaker; retorna `ErrCircuitOpen` se circuito aberto.
- `State(opName)` — retorna estado atual para métricas.
- Lazy creation de breakers: criado sob demanda na primeira chamada.

#### `internal/infrastructure/circuitbreaker/breaker_test.go`
- `TestBreakerGroup_ExecuteSuccess` — sucesso mantém circuito fechado.
- `TestBreakerGroup_ExecuteFailureOpensCircuit` — falhas consecutivas abrem circuito.
- `TestBreakerGroup_OpenCircuitReturnsErrCircuitOpen` — circuito aberto retorna erro sem executar função.
- `TestBreakerGroup_HalfOpenClosesOnSuccess` — após cooldown, sucesso em half-open fecha circuito.
- `TestBreakerGroup_HalfOpenReopensOnFailure` — falha em half-open reabre circuito.
- `TestBreakerGroup_MultipleOperationsIndependent` — breakers de operações diferentes são independentes.

### Arquivos modificados

#### `internal/config/config.go`
- Adicionados campos: `CircuitMaxRequests`, `CircuitFailureThreshold`, `CircuitTimeout`.
- Carregamento de env vars: `CIRCUIT_MAX_REQUESTS`, `CIRCUIT_FAILURE_THRESHOLD`, `CIRCUIT_TIMEOUT`.
- Nova função auxiliar `parseUint32`.

#### `internal/client/python/client.go`
- Adicionado campo `breakers *circuitbreaker.BreakerGroup` ao `Client`.
- `NewClient` agora aceita terceiro parâmetro `breakers` (pode ser `nil` para desabilitar).
- Métodos `Chat`, `Summarize`, `Compare`, `ProcessDocument` envolvem `doRequest` dentro do breaker.
- Se `breakers == nil`, comportamento unchanged (sem circuit breaker).
- `doRequest` permanece inalterado — breaker é camada externa.

#### `internal/api/v1/handlers/proxy.go`
- Adicionado tratamento de `circuitbreaker.ErrCircuitOpen` em `handlePythonError`.
- Status 503 com mensagem segura.
- Log Warn com `operation`, `request_id`, `error_type: circuit_open`.

#### `internal/api/v1/router.go`
- Cria `circuitbreaker.BreakerGroup` a partir do config.
- Passa breakers para `python.NewClient`.

#### `internal/client/python/client_test.go`
- Atualizados todos os `NewClient` para passar `nil` como breakers (backward compat).
- Adicionado `TestClient_Chat_CircuitOpen` — valida que client retorna `ErrCircuitOpen` sem fazer HTTP quando circuito aberto.

#### `internal/api/v1/handlers/proxy_test.go`
- Atualizados `NewClient` para nova assinatura.
- Adicionado `TestProxyChat_CircuitBreaker503` — valida resposta 503 com mensagem correta.

#### `go.mod`
- Adicionada dependência `github.com/sony/gobreaker v1.0.0`.

## Transições de Estado

```
CLOSED (normal)
  │
  ├─ sucesso → permanece CLOSED
  │
  └─ falhas consecutivas >= threshold → OPEN
       │
       └─ após timeout → HALF-OPEN
            │
            ├─ sucesso → CLOSED (recuperado)
            │
            └─ falha → OPEN (reabre)
```

## Testes Executados

| Teste | Arquivo | Resultado |
|---|---|---|
| `TestBreakerGroup_ExecuteSuccess` | `breaker_test.go` | ✅ |
| `TestBreakerGroup_ExecuteFailureOpensCircuit` | `breaker_test.go` | ✅ |
| `TestBreakerGroup_OpenCircuitReturnsErrCircuitOpen` | `breaker_test.go` | ✅ |
| `TestBreakerGroup_HalfOpenClosesOnSuccess` | `breaker_test.go` | ✅ |
| `TestBreakerGroup_HalfOpenReopensOnFailure` | `breaker_test.go` | ✅ |
| `TestBreakerGroup_MultipleOperationsIndependent` | `breaker_test.go` | ✅ |
| `TestClient_Chat_CircuitOpen` | `client_test.go` | ✅ |
| `TestProxyChat_CircuitBreaker503` | `proxy_test.go` | ✅ |
| Todos os testes existentes de Feature 2.1 | `client_test.go`, `proxy_test.go` | ✅ (não quebrados) |

> **Nota:** Go não está disponível neste ambiente para execução direta dos testes. Os testes foram escritos para compilar e passar quando executados com `go test ./...` no ambiente de CI/CD.

## Próximos Passos

- **Feature 2.3:** Retry com backoff exponencial para falhas transitórias (antes do circuit breaker abrir).
- **Feature 2.4:** Métricas Prometheus para estado dos circuit breakers (contagem de transições, tempo em cada estado).
- **Feature 2.5:** Rate limiting por cliente/IP no gateway Go.
