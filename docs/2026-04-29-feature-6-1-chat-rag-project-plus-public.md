# Feature 6.1 - Chat RAG com project plus public

## Contexto
Com o acervo publico indexado na Fase 5, esta feature habilita uso controlado dessa base no chat RAG.

## Decisoes tecnicas
- Introduzir modo de retrieval com feature flag.
- Preservar isolamento por `project_id` para dados privados.
- Exigir rastreabilidade de fontes com `source_type` e identificadores.

## Implementacao
Planejada para incluir:
- ajuste de retrieval no `python-agent`
- contratos internos para modo de busca
- fallback anti-alucinacao para baixa evidencia

## Testes executados
Nao aplicavel nesta etapa de documentacao. Execucao sera registrada durante implementacao da feature.

## Proximos passos
1. Definir contrato de modo de retrieval.
2. Implementar comparativo `project_only` vs `project_plus_public`.
