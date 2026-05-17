# Feature 3.1 — Cache semantico Redis no chat

## Contexto

A Feature 3.0 estabeleceu a linha de base de performance do endpoint `POST /api/v1/chat`:
p50=236ms, p95=256ms, p99=262ms, 41.6 req/s, com 0% de taxa de erro.

Cada requisicao de chat aciona o agente Python (FastAPI + Agno), que por sua vez
consulta o LLM para gerar resposta. Para perguntas repetidas ou semanticamente
equivalentes, esse fluxo gera latencia desnecessaria e custo computacional evitavel.

Esta feature implementa cache semantico com Redis no gateway Go para:

- Reduzir latencia de perguntas repetidas (cache hit retorna em ~1ms vs ~236ms)
- Diminuir chamadas ao agente Python, liberando capacidade para requisicoes novas
- Manter fallback seguro quando Redis esta indisponivel (bypass transparente)
- Preservar consistencia via normalizacao semantica da pergunta

## Decisoes tecnicas

- **Cache no gateway Go (nao no agente Python)**: interceptar antes da chamada remota
  evita round-trip HTTP desnecessario. O gateway ja e o ponto de entrada unico.
- **Padrao read-through**: verificar Redis antes de chamar Python; em cache miss,
  armazenar a resposta do Python no Redis para proximas consultas.
- **Formato da chave**: `chat:{project_id}:{question_hash}:{version}`
  - `project_id`: isola cache por projeto (documentos diferentes = contextos diferentes)
  - `question_hash`: SHA-256 da pergunta normalizada (evita caracteres problematicos)
  - `version`: versao do schema de cache (hardcoded=1 por enquanto)
- **Normalizacao da pergunta**: trim, lowercase, colapso de espacos multiplos,
  remocao de pontuacao nao-semantica (virgulas, pontos, hifens, parenteses).
  Garante que "O que e RAG?" e "o que e rag" produzam a mesma chave.
- **TTL configuravel**: variavel de ambiente `CACHE_TTL` (default: 5m).
  Expiracao automatica evita stale cache sem necessidade de invalidacao manual.
- **Fallback seguro**: se Redis falhar (conexao recusada, timeout, erro de rede),
  o cache e bypassado silenciosamente e a requisicao segue para o agente Python.
  Sem falha em cascata — Redis e otimizacao, nao dependencia critica.
- **Versao hardcoded=1**: Feature 3.2 tornara a versao dinamica por projeto,
  vinculada a versao dos documentos indexados. Por enquanto, versao fixa simplifica
  a implementacao inicial.
- **Fire-and-forget Set**: operacao `Set` no Redis executada em goroutine separada
  para nao atrasar a resposta ao cliente. Se falhar, log de warning apenas.

## Implementacao

### Arquivos criados

| Arquivo | Descricao |
|---|---|
| `services/go-gateway/internal/infrastructure/cache/cache.go` | SemanticCache com Get/Set/Close |
| `services/go-gateway/internal/infrastructure/cache/key.go` | NormalizeQuestion, BuildCacheKey |
| `services/go-gateway/internal/infrastructure/cache/cache_test.go` | Testes unitarios do cache |
| `docs/2026-04-28-feature-3-1-cache-semantico-redis-chat.md` | Este documento |

### Arquivos modificados

| Arquivo | Alteracao |
|---|---|
| `services/go-gateway/internal/config/config.go` | Adicionados CacheTTL, CacheEnabled, CacheMaxSize |
| `services/go-gateway/internal/api/v1/handlers/proxy.go` | ProxyChat verifica cache antes de chamar Python |
| `services/go-gateway/internal/api/v1/router.go` | Register passa instancia de cache para ProxyChat |
| `services/go-gateway/internal/app/app.go` | Inicializa SemanticCache, fecha no cleanup |
| `.env.example` | Adicionadas variaveis CACHE_TTL e CACHE_ENABLED |
| `services/go-gateway/internal/api/v1/handlers/proxy_test.go` | Atualizado para passar nil cache |
| `services/go-gateway/internal/api/v1/handlers/health_test.go` | Atualizado para passar nil cache |
| `services/go-gateway/internal/api/v1/handlers/observability_test.go` | Atualizado para passar nil cache |

### `cache.go` — SemanticCache

Estrutura principal com tres metodos publicos:

- `Get(ctx, key) ([]byte, bool, error)`: retorna valor do cache e hit/miss
- `Set(ctx, key, value, ttl)`: armazena valor com TTL (usado em fire-and-forget)
- `Close()`: fecha conexao com Redis

Cliente Redis configurado com timeout de 500ms para operacoes de leitura,
garantindo que cache miss nao adicione latencia significativa ao fallback.

### `key.go` — Normalizacao e construcao de chave

- `NormalizeQuestion(question string) string`: aplica pipeline de normalizacao
  (trim → lowercase → collapse spaces → remove non-semantic punctuation)
- `BuildCacheKey(projectID, question, version string) string`: normaliza pergunta,
  calcula SHA-256, monta chave no formato `chat:{project_id}:{hash}:{version}`

### `proxy.go` — Integracao no handler de chat

Fluxo do `ProxyChat` com cache:

1. Normaliza pergunta e constroi chave de cache
2. Tenta `cache.Get()` — se hit, retorna resposta imediatamente (pula Python)
3. Se miss ou erro de cache, chama agente Python normalmente
4. Se resposta do Python for valida, dispara `cache.Set()` em goroutine separada
5. Retorna resposta ao cliente

Cache nil (desabilitado ou nao inicializado) bypassa toda logica de cache
sem alteracao de comportamento.

### `config.go` — Novas variaveis de configuracao

| Variavel | Tipo | Default | Descricao |
|---|---|---|---|
| `CacheEnabled` | bool | true | Habilita/desabilita cache semantico |
| `CacheTTL` | time.Duration | 5m | Tempo de vida das entradas no cache |
| `CacheMaxSize` | int | 10000 | Tamanho maximo do pool de conexoes Redis |

### `app.go` — Inicializacao e cleanup

- Inicializa `SemanticCache` com `RedisURL`, `CacheTTL`, `CacheEnabled`
- Se Redis indisponivel na inicializacao, log de warning e cache opera em modo bypass
- Registra `cache.Close()` no defer de cleanup do app

## Testes executados

### Testes unitarios do cache

```bash
cd services/go-gateway
go test ./internal/infrastructure/cache/... -v
```

Cobertura:

- **NormalizeQuestion**: trim, lowercase, espacos multiplos, pontuacao removida,
  strings vazias, unicode, casos extremos
- **BuildCacheKey**: formato correto, consistencia (mesma entrada = mesma chave),
  project_id diferente = chave diferente, versao diferente = chave diferente
- **Cache desabilitado**: Get retorna miss, Set nao falha, Close e no-op
- **Cliente nil**: Get retorna miss sem erro, Set nao falha, comportamento seguro

### Testes existentes atualizados

```bash
go test ./internal/api/v1/handlers/... -v
```

- `proxy_test.go`: atualizado para passar `nil` como cache — testes continuam passando
- `health_test.go`: atualizado para passar `nil` como cache — testes continuam passando
- `observability_test.go`: atualizado para passar `nil` como cache — testes continuam passando

Todos os testes existentes passam sem alteracao de comportamento quando cache e nil.

### Teste de integracao (manual)

Cenario 1 — Cache hit:

```bash
# Primeira requisicao (miss, vai para Python)
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"project_id":"test","question":"O que e RAG?"}'

# Segunda requisicao com mesma pergunta (hit, retorna do Redis)
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"project_id":"test","question":"O que e RAG?"}'
```

Cenario 2 — Normalizacao semantica:

```bash
# Perguntas semanticamente equivalentes devem gerar cache hit
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"project_id":"test","question":"O que e RAG?"}'

curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"project_id":"test","question":"o que e rag"}'
```

Cenario 3 — Redis indisponivel:

```bash
# Parar Redis e verificar que requisoes continuam funcionando (bypass)
docker stop redis
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"project_id":"test","question":"O que e RAG?"}'
# Deve retornar resposta do Python sem erro
```

## Proximos passos

1. **Feature 3.2**: Invalidacao de cache por versao de documento do projeto
   - Vincular versao da chave de cache aos documentos indexados
   - Invalidar entradas quando documentos sao atualizados ou removidos
   - Implementar `version` dinamica por projeto (atualmente hardcoded=1)
2. **Feature 3.3**: Observabilidade de metricas de cache
   - Expor `cache_hits_total`, `cache_misses_total`, `cache_errors_total` via Prometheus
   - Adicionar header `X-Cache: HIT/MISS` nas respostas para debug
   - Dashboard Grafana com hit rate e latencia comparativa (hit vs miss)
3. **Benchmark comparativo**: Executar `chat_baseline.py` com cache ativo para
   medir reducao de latencia p95 e taxa de hit em carga realista
