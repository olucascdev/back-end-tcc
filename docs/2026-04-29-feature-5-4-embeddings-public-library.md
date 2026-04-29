# Feature 5.4 - Embeddings para Acervo Publico

**Data:** 2026-04-29
**Status:** Implementado

## Contexto

Com artefatos armazenados no MinIO (Feature 5.3), o pipeline de embeddings extrai texto, divide em chunks, gera vetores via OpenAI e persiste no NeonDB/pgvector. Isso habilita busca semantica futura no chat RAG sobre acervo publico.

## Decisoes Tecnicas

### TextExtractor

- Suporte a multiplos formatos: TXT (direto), EPUB (via `ebooklib`), PDF (via `pypdf` ou `pdfplumber`).
- Extracao defensiva: se parser falhar, retorna texto parcial em vez de erro fatal.
- Limite de tamanho: arquivos >50MB sao rejeitados antes da extracao.
- Normalizacao: remove espacos excessivos, normaliza unicode, preserva quebras de paragrafo.

### TextChunker

- Estrategia de chunking por tamanho fixo com overlap configuravel.
- Padrao: chunk_size=1000 tokens, overlap=200 tokens (estimativa por caracteres).
- Separadores preferenciais: paragrafo > frase > palavra (minimiza quebra de contexto).
- Metadados por chunk: `chunk_index`, `total_chunks`, `start_char`, `end_char`.

### OpenAIEmbedder

- Cliente async com `httpx` e retry com backoff.
- Batch de embeddings: agrupa chunks em lotes de ate 100 para reduzir chamadas API.
- Modelo padrao: `text-embedding-3-small` (dimensao 1536).
- Cache local em memoria para chunks repetidos dentro do mesmo job.

### PublicVectorStore

- Wrapper sobre `pgvector_store.py` com schema especifico para acervo publico.
- Insercao com `ON CONFLICT` por fingerprint (idempotencia).
- Busca por similaridade com filtro opcional de `source_provider` e `language`.

### EmbeddingProcessorUseCase

- Orquestra o pipeline: download do artefato > extracao > chunking > embed > persistencia.
- Fingerprint de idempotencia: `source_id + checksum + chunk_version`.
- Se fingerprint ja existir no vector store, pula geracao e reutiliza embedding.
- Metadata contract obrigatorio em cada embedding:

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `source_type` | string | `public_library` |
| `source_provider` | string | `gutenberg`, `openlibrary` |
| `source_id` | string | ID original na fonte |
| `artifact_key` | string | Chave no MinIO |
| `checksum` | string | SHA-256 do artefato |
| `chunk_version` | int | Versao do chunk (default: 1) |
| `chunk_index` | int | Indice do chunk no documento |
| `language` | string | Idioma do texto |

## Implementacao

### Arquivos Criados/Modificados

| Arquivo | Acao | Descricao |
|---------|------|-----------|
| `app/infrastructure/text_extraction.py` | Criado | TextExtractor com suporte TXT/EPUB/PDF, extracao defensiva, normalizacao |
| `app/infrastructure/chunking.py` | Criado | TextChunker com overlap, separadores inteligentes, metadados por chunk |
| `app/infrastructure/embedder.py` | Criado | OpenAIEmbedder com batching, retry, cache local, modelo text-embedding-3-small |
| `app/infrastructure/vector_store.py` | Criado | PublicVectorStore com schema pgvector, idempotencia por fingerprint, busca com filtros |
| `app/application/embedding_processor.py` | Criado | EmbeddingProcessorUseCase com pipeline completo e fingerprint idempotencia |
| `app/domain/models.py` | Modificado | Adicionados `TextChunk`, `EmbeddingRecord`, `EmbeddingFingerprint` |
| `tests/test_text_extraction.py` | Criado | 13 testes: txt, epub, pdf, extracao parcial, limite tamanho, normalizacao, erro parser |
| `tests/test_chunking.py` | Criado | 11 testes: tamanho fixo, overlap, separadores, chunks vazio, unicode, metadados |
| `tests/test_embedder.py` | Criado | 15 testes: batch, retry, cache, modelo, dimensao, erro api, timeout, vazio |
| `tests/test_vector_store.py` | Criado | 5 passed, 2 skip: insercao, busca, filtro, idempotencia, conexao; skip = sem pgvector running |
| `tests/test_embedding_processor.py` | Criado | 9 testes: pipeline completo, idempotencia, skip existente, erro extracao, batch, metadata contract |

## Testes Executados

```
$ pytest services/public-indexer/tests/test_text_extraction.py -v
13 passed in 0.48s

$ pytest services/public-indexer/tests/test_chunking.py -v
11 passed in 0.22s

$ pytest services/public-indexer/tests/test_embedder.py -v
15 passed in 0.61s

$ pytest services/public-indexer/tests/test_vector_store.py -v
5 passed, 2 skipped in 0.19s

$ pytest services/public-indexer/tests/test_embedding_processor.py -v
9 passed in 0.44s

---
Total Feature 5.4: 53 passed, 2 skipped
```

## Proximos Passos

- **Feature 5.5**: Retry robusto, agendamento com lock distribuido e fila de morte (DLQ) para falhas.

## Riscos Residuais

- EPUB/PDF parsers podem falhar em arquivos malformados — fallback para extracao parcial e log de warning.
- Custo OpenAI proporcional ao volume de chunks — monitorar em producao.
