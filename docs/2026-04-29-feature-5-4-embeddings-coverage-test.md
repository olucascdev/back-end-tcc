# Teste de Cobertura: Reindexacao por Mudanca de Checksum

## Contexto

Durante revisao GLM do codigo do `EmbeddingProcessorUseCase`, foi identificado que o caminho de codigo responsavel por limpar embeddings obsoletos quando o checksum de um artefato muda (linhas 173-186 de `embedding_processor.py`) nao possuia testes automatizados.

Este caminho executa quando:
1. Um livro ja existe no MongoDB com um checksum anterior
2. Um novo artefato e recebido com checksum diferente
3. Embeddings antigos devem ser removidos antes da insercao dos novos

Sem teste, regressoes neste fluxo de cleanup poderiam causar embeddings duplicados ou desatualizados no vector store.

## Decisoes Tecnicas

- **Abordagem**: Adicionar `delete_by_fingerprint` ao fixture `mock_vector_store` com valor padrao de retorno `1`, criando nova classe de testes `TestEmbeddingProcessorReindex`.
- **Isolamento**: Cada teste sobrescreve `mock_book_catalog.find_by_stable_key` para simular os tres cenarios (checksum antigo, checksum igual, documento inexistente).
- **Nao quebra existentes**: O fixture padrao de `find_by_stable_key` continua retornando `None`, mantendo comportamento dos testes anteriores intacto.

## Implementacao

### Arquivos modificados

- `services/public-indexer/tests/test_embedding_processor.py`
  - Linha 67: adicionado `delete_by_fingerprint = AsyncMock(return_value=1)` ao fixture `mock_vector_store`
  - Linhas 288-360: nova classe `TestEmbeddingProcessorReindex` com 3 testes

### Arquivos criados

- `docs/2026-04-29-feature-5-4-embeddings-coverage-test.md` — este arquivo

## Testes Executados

| Teste | Cenario | Assert principal |
|-------|---------|-----------------|
| `test_delete_old_embeddings_on_checksum_change` | Livro existe com checksum antigo, novo checksum diferente | `delete_by_fingerprint("42", "old_checksum_123")` chamado; `insert_embeddings` chamado; `result.success=True`, `result.skipped=False` |
| `test_no_delete_when_checksum_unchanged` | Livro existe com mesmo checksum | `delete_by_fingerprint` NAO chamado; `insert_embeddings` chamado |
| `test_no_delete_when_no_existing_doc` | Livro novo (sem documento no MongoDB) | `delete_by_fingerprint` NAO chamado; `insert_embeddings` chamado |

Todos os testes existentes continuam passando.

## Proximos Passos

Nenhum. Este teste fecha a lacuna identificada na revisao GLM.
