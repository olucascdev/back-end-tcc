# Planejamento Fase 6 - Qualidade, avaliacao e hardening final

## Contexto
A Fase 5 encerrou o indexador de acervo publico com pipeline completo e evidencias de estabilidade local. A Fase 6 consolida a qualidade tecnica e academica para fechamento do backend do TCC.

Escopo desta fase:
- consolidacao de testes Go e Python
- benchmark final de carga e resiliencia
- avaliacao RAG com metricas academicas
- hardening final de seguranca e operacao
- quality gates finais para fechamento

Fora de escopo desta fase:
- frontend e BFF
- novas features de produto fora dos fluxos definidos
- mudancas arquiteturais amplas sem OpenSpec dedicado

## Decisoes tecnicas
- Fluxo SDD obrigatorio via OpenSpec para toda capacidade nova da fase.
- Consumir acervo publico no chat RAG antes da avaliacao final para medir impacto real.
- Medicoes devem ser reproduziveis com dataset fixo, seed fixa e scripts versionados.
- Cada feature da fase gera documento dedicado em `docs/`.
- Criterio de aceite final combina qualidade tecnica (tests/performance) e qualidade academica (metricas RAG).

## Implementacao

### Feature 6.0 - Preflight e baseline de qualidade
Objetivo:
- congelar baseline tecnico e preparar ambiente de avaliacao.

Escopo tecnico:
- definir matriz de metas da fase (latencia, erro, throughput, resiliencia).
- congelar dataset de avaliacao (golden set) versionado.
- validar estado inicial de metricas, logs e health checks.

### Feature 6.1 - Consumo de acervo publico no chat RAG
Objetivo:
- habilitar modo de retrieval hibrido para usar acervo publico indexado.

Escopo tecnico:
- adicionar modo `project_plus_public` no `python-agent` com feature flag.
- manter isolamento de projeto e rastreabilidade de fontes.
- preservar politica anti-alucinacao para baixa evidencia.

### Feature 6.2 - Suite completa de testes Go e Python
Objetivo:
- fechar cobertura funcional dos caminhos criticos.

Escopo tecnico:
- ampliar unitarios e integracao em `go-gateway`, `python-agent` e `public-indexer`.
- criar smoke e2e com fluxo real de ingestao e chat.
- consolidar comando unico de execucao em CI.

### Feature 6.3 - Benchmark final de carga e resiliencia
Objetivo:
- comprovar comportamento sob carga normal e degradada.

Escopo tecnico:
- executar cenarios de chat repetido, chat inedito e ingestao concorrente.
- medir p50/p95/p99, RPS, error rate e recovery time.
- testar degradacao controlada de dependencias (Redis/Mongo/MinIO/Python).

### Feature 6.4 - Avaliacao RAG academica
Objetivo:
- gerar evidencias academicas reproduziveis de qualidade de resposta.

Escopo tecnico:
- rodar pipeline de avaliacao com metricas:
  - faithfulness
  - answer relevancy
  - context precision
  - context recall
- comparar resultados por modo de retrieval (`project_only` vs `project_plus_public`).

### Feature 6.5 - Hardening final de seguranca e operacao
Objetivo:
- elevar prontidao operacional para entrega final.

Escopo tecnico:
- reforcar protecao de endpoints administrativos e segredos.
- revisar redacao de logs sensiveis.
- definir alertas operacionais e runbooks de incidente.

### Feature 6.6 - Quality gates finais e fechamento
Objetivo:
- criar gate final unico para aceite da fase.

Escopo tecnico:
- unificar gates de testes, benchmark, avaliacao RAG, lint e seguranca.
- registrar checklist de conformidade final e riscos residuais.

## Criterios de aceite da fase
- metricas tecnicas coletadas e reproduziveis.
- benchmark final publicado com evidencia completa.
- metricas RAG publicadas por cenario e por modo de retrieval.
- hardening de seguranca e operacao concluido.
- quality gate final sem falhas bloqueantes.
- documentacao completa da fase publicada em `docs/`.

## Plano de documentacao da fase
- `docs/2026-04-29-feature-6-0-preflight-baseline-qualidade.md`
- `docs/2026-04-29-feature-6-1-chat-rag-project-plus-public.md`
- `docs/2026-04-29-feature-6-2-suite-testes-go-python-e2e.md`
- `docs/2026-04-29-feature-6-3-carga-resiliencia-benchmark-final.md`
- `docs/2026-04-29-feature-6-4-avaliacao-rag-metricas-academicas.md`
- `docs/2026-04-29-feature-6-5-hardening-seguranca-operacao.md`
- `docs/2026-04-29-feature-6-6-quality-gates-fechamento.md`
- `docs/2026-04-29-fase-6-conclusao-qualidade-avaliacao-hardening.md`
- `docs/2026-04-29-fase-6-readiness-checklist.md`

## Testes executados
Este documento representa planejamento da fase 6. Nao houve execucao de codigo nesta entrega.

## Proximos passos
1. Criar change OpenSpec `add-phase-6-quality-evaluation-hardening`.
2. Implementar na ordem 6.0 -> 6.1 -> 6.2 -> 6.3 -> 6.4 -> 6.5 -> 6.6.
3. Publicar um documento por feature com evidencias reais.
