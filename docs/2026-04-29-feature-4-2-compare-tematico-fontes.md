# Feature 4.2 — Comparação Temática com Fontes Rastreáveis

**Data:** 2026-04-29
**Status:** Implementado
**Serviço:** Python/FastAPI (`services/python-agent/`)

## Contexto

Após a implementação bem-sucedida da Feature 4.1 (Summarize real), esta feature implementa a comparação temática entre dois ou mais documentos acadêmicos, com fontes rastreáveis. O serviço Python recebe um tema e uma lista de `document_ids`, busca chunks relevantes no pgvector filtrados por `project_id`, agrupa por documento, chama o LLM para gerar uma comparação estruturada e retorna o resultado com citações.

## Decisões Técnicas

### 1. Padrão de serviço reutilizado do SummarizeService
- Mesma arquitetura em camadas: `CompareService` no domínio, endpoint no transport.
- Injeção de dependências via parâmetros opcionais (`settings`, `embedder`, `vector_store`).
- Fallback mock automático quando `OPENAI_API_KEY` não configurada.

### 2. Retrieval por tema (não por query fixa)
- Diferente do SummarizeService que usa query fixa, o CompareService gera embedding do `theme` informado pelo usuário.
- `top_k=15` para capturar contexto suficiente de múltiplos documentos.
- `min_score=0.5` para filtrar chunks irrelevantes.

### 3. Agrupamento por document_id
- Chunks são agrupados por `document_id` antes de montar o contexto.
- Contexto formatado com blocos claros (`=== DOCUMENTO: {id} ===`) para o LLM distinguir origens.

### 4. Parsing resiliente
- Primeira tentativa: JSON direto (com suporte a code blocks markdown).
- Segunda tentativa: regex/heurística para padrões como `similarities:`, `differences:`, `synthesis:`.
- Fallback final: valores padrão "Não identificado".

### 5. Validação mínima de contexto
- Requer chunks de pelo menos 2 documentos distintos para gerar comparação.
- Se insuficiente, retorna mensagem padronizada em todos os campos + sources vazias.

### 6. Fontes rastreáveis
- Extraídas dos chunks usados, com `document`, `page`, `section` e `score`.
- Ordenadas por score descendente para priorizar fontes mais relevantes.

## Implementação

### Arquivos criados/modificados

| Arquivo | Ação | Descrição |
|---------|------|-----------|
| `app/domain/compare_service.py` | Criado | `CompareService` com fluxo completo: embedding → busca → filtro → agrupamento → LLM → parsing → fontes |
| `app/api/v1/endpoints/compare.py` | Modificado | Substituído stub por chamada real ao `CompareService` |
| `tests/test_compare_service.py` | Criado | 12 testes unitários cobrindo contexto suficiente, fallback, parsing, isolamento e agrupamento |
| `tests/test_api_v1.py` | Modificado | Atualizados testes de integração do endpoint compare com mocks do CompareService |

### Fluxo do CompareService

```
compare(project_id, document_ids, theme)
  │
  ├─ 1. embedder.embed_query(theme) → query_embedding
  ├─ 2. vector_store.search_similar_by_project(project_id, query_embedding, top_k=15)
  ├─ 3. Filtra chunks por document_ids
  ├─ 4. Agrupa chunks por document_id
  ├─ 5. Se < 2 docs com chunks → retorna fallback
  ├─ 6. Monta contexto com blocos por documento
  ├─ 7. LLM com prompt acadêmico (temp=0.2, max_tokens=2048)
  ├─ 8. Parsing: JSON → regex/heurística → fallback
  ├─ 9. Extrai fontes dos chunks
  └─ 10. Retorna CompareResponse
```

### Prompt de Comparação

O prompt solicita ao LLM que retorne JSON com 3 chaves:
- `similarities`: pontos em comum entre os documentos sobre o tema
- `differences`: divergências ou abordagens distintas
- `synthesis`: síntese geral da comparação temática

## Testes Executados

### Testes unitários do CompareService (`test_compare_service.py`)

| Teste | Descrição | Status |
|-------|-----------|--------|
| `test_compare_returns_comparison_with_sources` | Comparação completa com 3 chaves e sources | ✅ |
| `test_compare_filters_by_document_ids` | Filtragem correta por document_ids | ✅ |
| `test_compare_returns_insufficient_when_no_chunks` | Fallback sem chunks | ✅ |
| `test_compare_returns_insufficient_when_only_one_doc_has_chunks` | Fallback com 1 doc | ✅ |
| `test_compare_returns_insufficient_when_chunks_from_unrequested_docs` | Fallback com docs não solicitados | ✅ |
| `test_parse_complete_json_response` | Parsing JSON completo | ✅ |
| `test_parse_incomplete_json_response` | Parsing JSON incompleto | ✅ |
| `test_parse_markdown_code_block_response` | Parsing code block markdown | ✅ |
| `test_parse_invalid_json_response_uses_heuristics` | Fallback heurístico | ✅ |
| `test_parse_completely_invalid_response` | Fallback total | ✅ |
| `test_isolation_by_project_id` | Isolamento por project_id | ✅ |
| `test_group_chunks_by_document` | Agrupamento por document_id | ✅ |
| `test_build_context_separates_documents` | Contexto com blocos separados | ✅ |
| `test_compare_with_three_documents` | Comparação com 3 documentos | ✅ |

### Testes de integração (`test_api_v1.py`)

| Teste | Descrição | Status |
|-------|-----------|--------|
| `test_compare_returns_comparison` | Endpoint com CompareService mockado, valida estrutura + sources | ✅ |
| `test_compare_returns_insufficient_context` | Endpoint com fallback de contexto insuficiente | ✅ |

### Testes de contratos (`test_contracts_v1.py`)

| Teste | Descrição | Status |
|-------|-----------|--------|
| `TestCompareRequest.*` | Validação de CompareRequest | ✅ (existente) |
| `TestCompareResponse.*` | Validação de CompareResponse | ✅ (existente) |

### Comando de execução

```bash
pytest services/python-agent/tests/test_api_v1.py \
       services/python-agent/tests/test_contracts_v1.py \
       services/python-agent/tests/test_compare_service.py
```

## Próximos Passos

1. **Feature 4.3** — Implementar endpoint de chat com histórico persistente e paginação de fontes.
2. **Feature 5.x** — Integrar gateway Go com os endpoints Python reais (process, chat, summarize, compare).
3. **Melhoria** — Adicionar cache semântico Redis para comparações frequentes com mesmo tema + documentos.
4. **Melhoria** — Implementar circuit breaker no gateway Go para chamadas ao serviço Python.
5. **Testes E2E** — Adicionar testes de integração com banco pgvector real em ambiente de staging.
