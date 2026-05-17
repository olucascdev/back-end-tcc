# Feature 3.2: Invalidacao por Versao de Documento do Projeto

## Contexto

O cache semantico Redis armazena respostas de chat RAG com chave `chat:{project_id}:{question_hash}:{version}`. Antes desta feature, `version` era hardcoded como `1` (`const cacheVersion = 1` em `key.go`). Isso significava que quando um novo documento era processado em um projeto, respostas cached antigas (baseadas em documentos anteriores) continuavam sendo servidas, pois a chave de cache nao mudava.

**Problema**: Usuario processa documento novo → faz pergunta → recebe resposta cached de antes do documento existir.

**Solucao**: Versao dinamica por projeto. Cada vez que um job de processamento de documento finaliza (sucesso ou erro), a versao do cache do projeto e incrementada no Redis. Respostas cached com versao antiga tornam-se automaticamente invalidas.

## Decisoes Tecnicas

### Invalidacao O(1) via Redis INCR
- Chave: `project_cache_version:{projectID}`
- Operacao: `INCR` atomica do Redis — O(1), sem locks, sem SCAN
- Cada projeto tem versao independente — isolamento total entre projetos
- Sem necessidade de deletar chaves de cache existentes (TTL natural as remove)
- Sem SCAN de padroes — evita operacao O(N) no Redis

### Fluxo de invalidacao
1. Job PDF finaliza (`ready` ou `error`)
2. Worker chama `IncrementProjectCacheVersion()` → Redis INCR
3. Proxima requisicao de chat le versao atual via `GetProjectCacheVersion()`
4. Chave de cache construida com nova versao → cache miss intencional → resposta fresca do Python

### Fallback seguro
- Se Redis indisponivel para leitura da versao → fallback para `0` (log warning)
- Se cache desabilitado → metodos retornam `0, nil` (no-op)
- Se `redis.Nil` (primeira vez) → versao `0`

### Isolamento por projeto
- Chave inclui `projectID` → projetos nao interferem entre si
- Documento processado em projeto A nao invalida cache do projeto B

## Implementacao

### Arquivos modificados

#### `internal/infrastructure/cache/cache.go`
- Adicionado `GetProjectCacheVersion(ctx, projectID) (int, error)`
  - Chave: `project_cache_version:{projectID}`
  - `redis.Nil` → retorna `0, nil`
  - Import `strconv` para parse do valor
- Adicionado `IncrementProjectCacheVersion(ctx, projectID) (int, error)`
  - Usa `redisClient.Incr()` para operacao atomica
  - Retorna nova versao
- Ambos retornam `0, nil` se cache desabilitado ou `redisClient` nil

#### `internal/infrastructure/cache/key.go`
- Removida constante `const cacheVersion = 1`
- `BuildCacheKey` ja aceitava `version int` como parametro — sem alteracao na assinatura

#### `internal/api/v1/handlers/proxy.go`
- `ProxyChat` agora le versao dinamica antes de construir chave de cache
- `GetProjectCacheVersion` chamado com fallback para `0` em caso de erro
- Log warning se falha ao obter versao

#### `internal/infrastructure/queue/worker.go`
- Adicionado campo `semanticCache *cache.SemanticCache` ao struct `WorkerPool`
- `NewWorkerPool` e `NewWorkerPoolWithWebhook` agora aceitam `semanticCache` como ultimo parametro
- Adicionado metodo `maybeInvalidateCache(job)` — helper que incrementa versao se cache disponivel
- Chamado ao final de ambos os caminhos: sucesso (`StatusReady`) e erro (`StatusError`)
- Import do pacote `cache` adicionado

#### `internal/app/app.go`
- Chamada `NewWorkerPoolWithWebhook` atualizada para passar `semanticCache`

### Arquivos criados

#### `internal/infrastructure/cache/cache_test.go` (testes adicionados)
- `TestSemanticCache_GetProjectCacheVersion_Disabled` — cache desabilitado retorna `0, nil`
- `TestSemanticCache_GetProjectCacheVersion_NilClient` — client nil retorna `0, nil`
- `TestSemanticCache_IncrementProjectCacheVersion_Disabled` — cache desabilitado retorna `0, nil`
- `TestSemanticCache_IncrementProjectCacheVersion_NilClient` — client nil retorna `0, nil`

## Testes Executados

```bash
cd services/go-gateway
go test ./internal/infrastructure/cache/... -v
go test ./internal/api/v1/handlers/... -v
go build ./...
```

- Testes de cache: 4 novos testes para metodos de versao (disabled + nil client)
- Testes de handler: `ProxyChat(client, nil)` continua funcionando (semanticCache nil = no-op)
- Build: compilacao sem erros

## Proximos Passos

1. **TTL para chaves de versao**: Adicionar TTL as chaves `project_cache_version:{projectID}` para evitar crescimento ilimitado no Redis (ex: 30 dias sem atividade → versao expira)
2. **Invalidacao seletiva**: Se apenas um documento especifico for deletado, invalidar apenas cache relacionado aquele documento (requer mapeamento documento→cache)
3. **Metricas**: Adicionar contador Prometheus para invalidacoes de cache por projeto
4. **Testes com Redis real**: Testes de integracao com Redis em container para validar comportamento de INCR e GET em cenarios reais
