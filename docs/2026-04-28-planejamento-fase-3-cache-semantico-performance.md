# Planejamento Fase 3 - Cache semantico e performance

## Contexto
A Fase 2 entregou resiliencia operacional no gateway Go (timeout por operacao, retry idempotente, circuit breaker, rate limiting, fila de PDF e webhook). O proximo passo e reduzir latencia e custo computacional em perguntas repetidas no chat RAG.

Escopo desta fase:
- cache semantico Redis no caminho de chat
- invalidacao consistente por mudanca de corpus do projeto
- observabilidade de cache (hit/miss/latencia)
- benchmark com evidencia comparativa (baseline vs cache)

Fora de escopo nesta fase:
- evolucao do indexador publico
- avaliacao RAG academica (faithfulness/relevancy/recall/precision)
- novas features de produto (summarize/compare avancados)

## Decisoes tecnicas
- Cache aplicado no gateway Go (nao no Python agent) para reduzir chamadas remotas e manter ponto unico de orquestracao.
- Primeira entrega focada em `POST /api/v1/chat`.
- Estrategia de chave:
  - `project_id`
  - `normalized_question_hash`
  - `project_cache_version` (namespace logico para invalidacao O(1))
- Normalizacao semantica minima da pergunta:
  - trim
  - lowercase
  - colapso de espacos
  - remocao de pontuacao nao semantica
- Politica de expiracao:
  - TTL configuravel por ambiente (`CACHE_TTL`)
  - fallback seguro quando Redis indisponivel (bypass para Python)
- Invalidação por versao de cache por projeto (evita `SCAN` global em Redis).
- Metricas obrigatorias para governanca de performance:
  - `semantic_cache_hits_total`
  - `semantic_cache_misses_total`
  - `semantic_cache_errors_total`
  - `semantic_cache_latency_seconds`
  - `semantic_cache_hit_ratio`

## Implementacao

### Feature 3.0 - Baseline de performance + gate tecnico
Escopo:
- validar fluxo Go -> Python do endpoint de chat para benchmark sem vies
- executar baseline com cache desligado
- capturar p50/p95/p99, taxa de erro e volume de chamadas ao Python

Criterios de aceite:
- baseline reproduzivel documentado
- metricas base registradas antes da ativacao de cache

### Feature 3.1 - Cache semantico Redis no chat
Escopo:
- adicionar camada read-through no gateway para `chat`
- buscar em Redis antes da chamada ao Python
- em miss, chamar Python e persistir resposta no cache
- manter compatibilidade do contrato de resposta atual

Criterios de aceite:
- hit retorna resposta sem chamada ao Python
- miss popula cache com TTL
- falha de Redis nao quebra fluxo (fallback para upstream)

### Feature 3.2 - Invalidação por novo documento no projeto
Escopo:
- incrementar `project_cache_version` quando documento mudar estado relevante (`ready`/`error`)
- compor chave de cache com versao ativa
- evitar invalidacao custosa por varredura global

Criterios de aceite:
- apos nova ingestao, respostas antigas do projeto deixam de ser reutilizadas
- invalidacao nao impacta projetos nao relacionados

### Feature 3.3 - Observabilidade de cache
Escopo:
- adicionar metricas de hit/miss/error/latencia
- enriquecer logs com `cache_status`, `project_id`, `question_hash`, `cache_version`
- incluir contadores de bypass por indisponibilidade Redis

Criterios de aceite:
- metricas aparecem em `/metrics`
- logs permitem rastrear decisao hit/miss por requisicao

### Feature 3.4 - Benchmark e evidencias de ganho
Escopo:
- executar cenarios equivalentes com cache off/on:
  - perguntas repetidas
  - perguntas semanticamente equivalentes
  - perguntas ineditas
  - concorrencia moderada
- comparar latencia e offload de chamadas Python

Metas recomendadas:
- reducao p95 >= 25% em perguntas repetidas
- reducao de chamadas ao Python >= 30% em workload repetitivo
- hit ratio >= 40% em cenario com repeticao controlada

Criterios de aceite:
- relatorio com metodologia, configuracoes e resultados brutos
- conclusao objetiva de ganho ou gargalos remanescentes

### Feature 3.5 - Hardening opcional (recomendado)
Escopo:
- migrar rate limiting in-memory para backend Redis compartilhado
- preparar consistencia de limite em multiplas instancias do gateway

Criterios de aceite:
- limite consistente entre replicas
- sem regressao no contrato de erro `429`

### Artefatos esperados
- `services/go-gateway/internal/api/v1/handlers/*`
- `services/go-gateway/internal/infrastructure/cache/*`
- `services/go-gateway/internal/infrastructure/ratelimit/*` (se hardening 3.5)
- `services/go-gateway/internal/config/*`
- `services/go-gateway/internal/app/*`
- `docs/*feature-3-*.md`
- `docs/*fase-3*.md`

## Testes executados
Este documento representa planejamento e definicao de escopo da Fase 3.

Testes obrigatorios durante execucao:
- unitarios:
  - normalizacao de pergunta
  - geracao de chave de cache
  - serializacao/deserializacao de payload
  - regras de TTL
  - invalidacao por versao de projeto
- integracao:
  - hit sem chamada ao Python
  - miss com escrita em cache
  - bypass quando Redis indisponivel
  - isolamento por `project_id`
- carga/performance:
  - baseline cache off
  - cache on com mesma carga e dataset
  - comparativo p50/p95/p99, RPS, error rate, chamadas ao Python

## Proximos passos
1. Abrir change OpenSpec dedicado da Fase 3 (ex.: `add-phase-3-semantic-cache-performance`) com `proposal.md`, `tasks.md` e deltas de spec.
2. Executar na ordem: baseline -> cache chat -> invalidacao por versao -> observabilidade -> benchmark -> hardening opcional.
3. Gerar um documento por feature concluida (`docs/2026-04-28-feature-3-x-*.md`) com evidencias de teste.
4. Consolidar conclusao da fase em `docs/2026-04-28-fase-3-conclusao-cache-performance.md`.
