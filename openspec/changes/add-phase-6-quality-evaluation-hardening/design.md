## Context

Phase 5 completou indexação pública com `public-catalog-indexer`, MongoDB, MinIO e embeddings `source_type=public_library` no NeonDB/pgvector. O chat RAG do agente Python ainda opera apenas em modo `project_only`, deixando o acervo público não consumido. A entrega do TCC exige evidências de qualidade (testes, métricas acadêmicas RAG, benchmark de carga) e hardening operacional.

## Goals / Non-Goals

- Goals:
  - Habilitar consumo do acervo público no chat com rastreabilidade
  - Entregar testes unitários e de integração para Go e Python
  - Executar benchmark de carga e resiliência com resultados reprodutíveis
  - Avaliar RAG com métricas acadêmicas sobre golden dataset versionado
  - Hardening de segurança (auth admin) e operações (logs, alertas, runbooks)
  - Fechar phase com quality gate e relatório de compliance
- Non-Goals:
  - Reescrever frontend ou BFF
  - Alterar schema de embeddings existente (apenas adicionar consulta)
  - Substituição de LLM ou mudança de embedding model
  - Multi-region ou DR

## Decisions

- **Retrieval mode flag**: request de chat aceita `retrieval_mode` (`project_only` | `project_plus_public`). Default `project_only` para preservar comportamento atual e permitir rollout controlado via feature flag.
  - Alternatives considered: header customizado ou path separado; rejeitados por poluir API e aumentar manutenção.
- **Evaluation dataset versioning**: golden dataset versionado em `docs/evaluation/golden-dataset-v{major}.{minor}.json` com schema fixo (question, expected_context_ids, reference_answer). Reproducibilidade garantida por seed fixa e pinning de modelo.
  - Alternatives considered: armazenar no DB; rejeitado por complexidade desnecessária para TCC.
- **Benchmark methodology**: endpoint Go inicia benchmark via workers concorrentes contra endpoints reais em ambiente de staging; métricas coletadas por middleware de request logging. Não usa ferramenta externa para manter stack controlado.
  - Alternatives considered: k6/locust; rejeitados para evitar nova dependência e manter integração com circuit breaker/métricas internas.
- **Security hardening scope**: proteção de endpoints admin por JWT scope `admin`; redação de logs por middleware antes de escrita. Alertas via estrutura de log padronizada (não pager externo).
  - Alternatives considered: OAuth2 completo; rejeitado por escopo de TCC.

## Risks / Trade-offs

- **Risco: latência aumenta com recuperação pública** → Mitigação: limite de top_k por source_type e feature flag para desabilitar
- **Risco: benchmark em staging não reflete produção** → Mitigação: documentar limitação no relatório e usar como tendência relativa
- **Risco: métricas acadêmicas de evaluation são custosas (LLM-as-a-judge)** → Mitigação: pipeline executável sob demanda, não em CI; caching de judgments
- **Risco: cobertura de testes gera pressão de tempo** → Mitigação: priorizar integração sobre 100% unitário; smoke e2e como gate mínimo
- **Trade-off: feature flag adiciona complexidade** → Aceitável para permitir rollback instantâneo e comparação A/B no TCC

## Migration Plan

1. Ativar feature flag `ENABLE_PUBLIC_RETRIEVAL=false` em todos os ambientes (default seguro)
2. Fazer deploy do agente Python com novo retrieval mode e contrato de chat
3. Executar smoke e2e para validar regressão em `project_only`
4. Ativar `ENABLE_PUBLIC_RETRIEVAL=true` em staging e rodar evaluation
5. Fazer deploy do gateway Go com endpoints de benchmark e auth admin
6. Executar benchmark de carga e documentar resultados
7. Rodar quality gate e gerar relatório de compliance
8. Rollback: desabilitar feature flag ou reverter para imagem anterior do serviço afetado

## Open Questions

- Threshold mínimo aceitável para cada métrica acadêmica RAG (definir após primeira execução do pipeline)
- Ambiente de staging tem infraestrutura suficiente para benchmark representativo?
- Scope `admin` do JWT já existe no auth provider ou precisa de emissão manual?
