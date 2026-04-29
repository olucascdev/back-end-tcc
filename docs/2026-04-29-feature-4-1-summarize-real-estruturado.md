# Feature 4.1 — Summarize Real Estruturado

**Data:** 2026-04-29
**Status:** Implementado

## Contexto

O endpoint de resumo (`/api/v1/summarize/summarize-document`) retornava apenas dados mock. Esta feature implementa o fluxo real de resumo estruturado usando RAG: busca chunks relevantes no pgvector, chama LLM com prompt academico deterministico e retorna resumo com 4 secoes (objective, methodology, results, conclusion).

## Decisoes Tecnicas

- **Reutilizacao de padrao RAGService**: O `SummarizeService` segue o mesmo padrao de injecao de dependencias e chamada ao LLM do `RAGService`, mantendo consistencia na codebase.
- **Query fixa para embedding**: Usa `"summarize structured academic document"` como query fixa, pois o objetivo e recuperar chunks genericamente relevantes para resumo, nao responder pergunta especifica.
- **Filtro por document_id no dominio**: O `PgVectorStore.search_similar_by_project` filtra apenas por `project_id`. O filtro por `document_id` e feito em memoria no servico, evitando alteracao no contrato do repositorio.
- **Temperatura 0.2**: Baixa temperatura para respostas deterministicas e reprodutiveis.
- **Parsing robusto**: Tenta extrair JSON da resposta, remove code blocks markdown, preenche chaves ausentes com `"Nao identificado"`.
- **Fallback mock**: Quando `OPENAI_API_KEY` nao esta configurada, usa resposta mock baseada no contexto, mantendo compatibilidade com desenvolvimento local.
- **Sem alteracao breaking nos schemas**: `SummarizeRequest` e `SummarizeResponse` permanecem inalterados.

## Implementacao

### Arquivos criados

- `app/domain/summarize_service.py` — `SummarizeService` com metodo `summarize(project_id, document_id)`.
- `tests/test_summarize_service.py` — 9 testes unitarios cobrindo contexto suficiente, insuficiente, parsing e isolamento.

### Arquivos modificados

- `app/api/v1/endpoints/summarize.py` — Substituido stub por chamada real ao `SummarizeService`.
- `tests/test_api_v1.py` — Adicionados 2 testes de integracao com `SummarizeService` mockado (sucesso e fallback).

### Fluxo do SummarizeService

1. Gera embedding da query fixa via `OpenAIEmbedder.embed_query()`.
2. Busca chunks similares via `PgVectorStore.search_similar_by_project()` (top_k=10, min_score=0.5).
3. Filtra chunks onde `metadata['document_id'] == document_id`.
4. Se < 1 chunk → retorna `SummarizeResponse` com `"Contexto insuficiente para gerar resumo."`.
5. Monta contexto com limite de tokens (`MAX_CONTEXT_TOKENS * 4` chars).
6. Chama LLM com prompt academico deterministico (temp=0.2, max_tokens=2048).
7. Faz parsing da resposta JSON, preenchendo chaves ausentes com `"Nao identificado"`.
8. Retorna `SummarizeResponse` estruturado.

## Testes Executados

### Testes unitarios (test_summarize_service.py)

| Teste | Cenario | Resultado |
|-------|---------|-----------|
| `test_summarize_returns_structured_summary` | Contexto suficiente, 4 chaves | ✅ |
| `test_summarize_filters_by_document_id` | Filtragem por document_id | ✅ |
| `test_summarize_returns_insufficient_when_no_chunks` | Vector store vazio | ✅ |
| `test_summarize_returns_insufficient_when_no_matching_document` | Chunks de outro doc | ✅ |
| `test_parse_complete_json_response` | JSON completo do LLM | ✅ |
| `test_parse_incomplete_json_response` | JSON parcial (2/4 chaves) | ✅ |
| `test_parse_markdown_code_block_response` | JSON com code block | ✅ |
| `test_parse_invalid_json_response` | Texto nao-JSON | ✅ |
| `test_isolation_by_project_id` | Isolamento por projeto | ✅ |
| `test_isolation_by_document_id` | Isolamento por documento | ✅ |

### Testes de integracao (test_api_v1.py)

| Teste | Cenario | Resultado |
|-------|---------|-----------|
| `test_summarize_returns_structured_summary` | SummarizeService mockado, sucesso | ✅ |
| `test_summarize_returns_insufficient_context` | Fallback sem chunks | ✅ |

### Testes de contratos (test_contracts_v1.py)

| Teste | Cenario | Resultado |
|-------|---------|-----------|
| Todos os testes existentes | Validacao de schemas | ✅ (inalterados) |

## Proximos Passos

- Implementar `CompareService` (Feature 4.2) seguindo mesmo padrao.
- Adicionar cache semantico Redis para resumos ja gerados.
- Implementar streaming de resposta para documentos grandes.
- Adicionar metricas Prometheus para tempo de resumo e taxa de fallback.
