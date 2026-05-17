# Planejamento Fase 4 - Features academicas avancadas

## Contexto
Fase 4 foca valor academico direto no backend do assistente RAG. Escopo fechado desta fase:
- summarize real de documento
- compare tematico entre documentos
- sugestao de lacunas de pesquisa com rastreabilidade

Fora de escopo nesta fase:
- exportacao de conversas/analises
- evolucao do indexador publico
- mudancas de frontend/BFF

## Decisoes tecnicas
- Implementacao principal no `services/python-agent` (logica semantica).
- `services/go-gateway` permanece como camada de orquestracao/resiliencia/proxy.
- Contratos internos v1 devem permanecer compativeis; evitar breaking change.
- Toda resposta academica deve ter formato estruturado e rastreabilidade de fontes.
- Politica anti-alucinacao obrigatoria: sem evidencia suficiente, retornar limitacao explicita.
- Fluxo SDD obrigatorio via OpenSpec antes de codigo:
  - `openspec/changes/add-phase-4-academic-features/proposal.md`
  - `openspec/changes/add-phase-4-academic-features/tasks.md`
  - `openspec/changes/add-phase-4-academic-features/design.md`

## Implementacao

### Bloco 0 - Preflight e governanca
1. Criar change OpenSpec da fase 4 e validar em modo strict.
2. Alinhar rotas e contratos Go/Python para summarize e compare.
3. Corrigir observabilidade de paths no Python para extrair `project_id`, `document_id`, `session_id` corretamente.
4. Validar consistencia de schema de embeddings usado em runtime e migrations.

### Feature 4.1 - Summarize real estruturado
Objetivo:
- substituir stub atual por resumo real com formato estavel.

Escopo tecnico:
- criar `SummarizeService` no Python.
- recuperar contexto por `project_id` e `document_id`.
- gerar resposta estruturada com chaves obrigatorias:
  - `objective`
  - `methodology`
  - `results`
  - `conclusion`
- validar/parsing estrito da estrutura de saida.
- aplicar fallback quando contexto for insuficiente.

Criterios de aceite:
- endpoint retorna estrutura completa em cenario valido.
- endpoint retorna limitacao explicita em cenario sem contexto.
- contrato v1 mantido sem regressao.

### Feature 4.2 - Compare documents tematico com fontes
Objetivo:
- substituir stub atual por comparacao tematica real orientada a evidencias.

Escopo tecnico:
- criar `CompareService` no Python.
- processar comparacao para 2..N documentos por `theme`.
- produzir estrutura com:
  - `similarities`
  - `differences`
  - `synthesis`
- anexar `sources` rastreaveis (document, page, score).
- aplicar regra anti-alucinacao para baixa evidencia.

Criterios de aceite:
- comparacao retorna campos estruturados + fontes.
- requests invalidas seguem contrato de erro padronizado.
- isolamento por `project_id` preservado.

### Feature 4.3 - Sugestao de lacunas de pesquisa
Objetivo:
- adicionar capability para sugerir gaps com base no corpus do projeto.

Escopo tecnico:
- criar endpoint dedicado no Python + proxy correspondente no Go.
- criar `ResearchGapService` para:
  - mapear cobertura tematica
  - identificar lacunas por baixa cobertura/conflito/ausencia de evidencia
  - gerar recomendacoes de perguntas futuras
- saida estruturada por lacuna:
  - `gap_title`
  - `why_gap`
  - `evidence_sources`
  - `suggested_questions`
  - `confidence` (`low|medium|high`)

Criterios de aceite:
- endpoint retorna lista de lacunas com fontes e confianca.
- corpus insuficiente retorna resposta explicita e segura.
- contratos Go/Python versionados e consistentes.

### Hardening transversal da fase
- revisar timeout/retry/circuit breaker no gateway para novas operacoes.
- padronizar payload de erro e logs estruturados entre summarize/compare/lacunas.
- reforcar metricas por operacao e correlacao via `request_id`.

## Testes executados
Este documento representa planejamento da fase 4. Nao ha execucao de codigo nesta entrega.

Testes obrigatorios durante execucao:
- Unitarios (Python):
  - summarize parser/estrutura/fallback
  - compare agregacao/ranking/sources
  - lacunas cobertura/confianca/serializacao
- Integracao (Python API):
  - sucesso e falha para summarize, compare e lacunas
  - cenarios de contexto insuficiente
- Gateway Go:
  - handlers/proxy para summarize, compare e lacunas
  - mapeamento de erro upstream coerente
- Regressao:
  - chat/process-document sem quebra de comportamento
  - contratos v1 validados

## Cronograma recomendado (Semanas 12-15)
1. Semana 12: preflight + OpenSpec + Feature 4.1.
2. Semana 13: Feature 4.2 + testes.
3. Semana 14: Feature 4.3 + testes.
4. Semana 15: hardening transversal + evidencias finais + conclusao da fase.

## Definition of Done da Fase 4
- Summarize real em producao local com estrutura estavel.
- Compare real com rastreabilidade de fontes.
- Lacunas de pesquisa com evidencias e confianca.
- Testes unitarios/integracao Go+Python passando.
- OpenSpec da fase validado com `--strict`.
- Documentacao de features e conclusao publicadas em `docs/`.

## Proximos passos
1. Criar change OpenSpec `add-phase-4-academic-features` e submeter para aprovacao.
2. Implementar features na ordem 4.1 -> 4.2 -> 4.3.
3. Gerar documentos de execucao por feature em PT-BR:
   - `docs/2026-04-29-feature-4-1-summarize-real-estruturado.md`
   - `docs/2026-04-29-feature-4-2-compare-tematico-fontes.md`
   - `docs/2026-04-29-feature-4-3-lacunas-pesquisa.md`
4. Consolidar fechamento em `docs/2026-04-29-fase-4-conclusao-features-academicas.md`.
