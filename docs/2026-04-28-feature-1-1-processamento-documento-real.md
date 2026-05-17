# Feature 1.1 - Processamento real de documento

## Contexto

Apos o bootstrap do servico Python/FastAPI (Feature 4) com stubs retornando respostas mock, era necessario implementar o pipeline real de processamento de documentos academicos. Sem extracao de texto, chunking, embeddings e persistencia vetorial, o sistema nao consegue alimentar a base de conhecimento para operacoes RAG (chat com fontes, resumo, comparacao).

Esta feature resolve:
- extrair texto de PDFs pagina a pagina
- dividir texto em chunks com overlap para preservar contexto
- gerar embeddings vetoriais via OpenAI API
- persistir chunks e embeddings no PostgreSQL com extensao pgvector
- atualizar status do documento no NeonDB
- cobrir todo o pipeline com testes unitarios e de integracao

## Decisoes tecnicas

### PyPDF2 para extracao de texto
- PyPDF2 escolhido por maturidade, API simples e compatibilidade com a maioria de PDFs academicos.
- Alternativa `pypdf` (fork moderno do PyPDF2) considerada, mas PyPDF2 ja atendia requisitos iniciais.
- Extracao pagina a pagina preserva metadata de `page_number` para rastreabilidade nas fontes RAG.
- PDFs invalidos ou corrompidos levantam `ValueError` com mensagem descritiva.
- **Nota**: PyPDF2 emite warning de deprecacao recomendando migracao para `pypdf` — migracao planejada para iteracao futura.

### Chunking com overlap
- Chunking por tamanho fixo de caracteres (default 1000) com overlap configuravel (default 200).
- Overlap garante que contexto nao seja perdido nas bordas entre chunks — essencial para qualidade de retrieval RAG.
- Quebra tenta ocorrer em limite de palavra (ultimo espaco) para evitar cortes no meio de termos tecnicos.
- Cada chunk carrega metadata: `page_number`, `chunk_index`, `project_id`, `document_id`.
- `TextChunker.chunk_pages()` processa todas as paginas extraidas e retorna lista plana de chunks.
- Protecao contra loop infinito quando overlap >= chunk_size (ajuste automatico para `chunk_size // 2`).

### OpenAI embeddings com fallback mock
- Modelo `text-embedding-3-small` (dimensao 1536) via OpenAI API.
- Processamento em batches (default 100) para evitar rate limit.
- **Fallback mock**: quando `OPENAI_API_KEY` nao esta configurada, gera embeddings deterministicos via hash MD5 do texto + vetor gaussiano normalizado. Permite desenvolvimento e testes sem dependencia externa.
- Embeddings mock sao consistentes (mesmo texto → mesmo vetor) e unitarios (norma = 1), compativeis com busca por distancia no pgvector.
- Custom exception `EmbeddingError` para falhas na API.

### pgvector para persistencia e busca vetorial
- Tabela `document_embeddings` com colunas: `content` (texto), `embedding` (vector(1536)), `metadata` (JSONB).
- Insercao bulk via `psycopg2.extras.execute_values` (page_size=100) para performance.
- Busca similar usa operador `<->` (distancia L2) do pgvector com filtro por `project_id`.
- Score de similaridade calculado como `1.0 - distance` para interpretacao intuitiva.
- `ThreadedConnectionPool` (minconn=1, maxconn=5) para gerenciamento de conexoes.
- `metadata` em JSONB permite flexibilidade sem alteracoes de schema.

## Implementacao

### Pipeline completo

O pipeline de processamento executa de forma sincrona no endpoint `POST /api/v1/documents/process-document`:

```
Request (ProcessDocumentRequest)
  │
  ├─ 1. Download MinIO/S3
  │     MinIOClient.download_file(storage_key) → file_bytes
  │
  ├─ 2. Extracao de texto
  │     PDFExtractor.extract_text(file_bytes) → pages[{page_number, text}]
  │
  ├─ 3. Chunking
  │     TextChunker.chunk_pages(pages, chunk_size, overlap) → chunks[{text, page_number, chunk_index}]
  │
  ├─ 4. Geracao de embeddings
  │     OpenAIEmbedder.embed_texts(chunk_texts) → embeddings[list[float]]
  │
  ├─ 5. Persistencia no pgvector
  │     PgVectorStore.insert_embeddings(embeddings_data) → count
  │     embeddings_data = [{content, embedding, metadata: {project_id, document_id, page_number, chunk_index}}]
  │
  ├─ 6. Atualizacao de status no NeonDB
  │     update_document_status(document_id, status="ready", chunks_count)
  │
  └─ Response (ProcessDocumentResponse)
        {document_id, status="ready", chunks_count, processed_at, error_message}
```

### Arquivos implementados

#### `app/infrastructure/extractors/pdf_extractor.py`
- Classe `PDFExtractor` com metodo `extract_text(file_bytes)`.
- Usa `PyPDF2.PdfReader` para leitura pagina a pagina.
- Retorna lista de dicts com `page_number` (1-based) e `text`.
- Trata `PdfReadError` convertendo para `ValueError`.

#### `app/infrastructure/chunking/chunker.py`
- Classe `TextChunker` com metodos `chunk_text()` e `chunk_pages()`.
- `chunk_text(text, chunk_size=1000, overlap=200, page_number=1)` divide texto preservando contexto.
- `chunk_pages(pages, chunk_size, overlap)` aplica chunking em todas as paginas.
- Quebra em limite de palavra quando possivel.

#### `app/infrastructure/embeddings/openai_embedder.py`
- Classe `OpenAIEmbedder` com metodo `embed_texts(texts, batch_size=100)`.
- Usa `openai.OpenAI` client quando `OPENAI_API_KEY` configurada.
- Fallback mock deterministic via `_mock_embed()` quando API key ausente.
- Embeddings mock: hash MD5 → seed → vetor gaussiano → normalizacao unitaria.
- Exception `EmbeddingError` para falhas de API.

#### `app/infrastructure/database/pgvector_store.py`
- Classe `PgVectorStore` com metodos `insert_embeddings()` e `search_similar()`.
- `insert_embeddings(embeddings_data)`: insercao bulk com `execute_values`.
- `search_similar(project_id, query_embedding, top_k=5)`: busca por distancia L2 com filtro por projeto.
- `ThreadedConnectionPool` para gerenciamento de conexoes.
- Metodo `close()` para encerrar pool.

#### `app/api/v1/endpoints/documents.py`
- Endpoint `POST /process-document` com modelo de resposta `ProcessDocumentResponse`.
- Funcao `_process_document_sync()` orquestra as 6 etapas do pipeline.
- Tratamento de erro por tipo:
  - `FileNotFoundError` → 404 (arquivo nao encontrado no storage)
  - `ValueError` → 400 (PDF invalido ou erro de validacao)
  - `StorageError` → 502 (erro de conexao com storage)
  - `Exception` generico → 500 (erro interno)
- Em caso de erro, atualiza status do documento para `error` no NeonDB via `_set_document_error()`.

### Configuracion

Parametros configuraveis via `Settings` (Pydantic Settings):
- `CHUNK_SIZE`: tamanho maximo do chunk (default 1000)
- `CHUNK_OVERLAP`: overlap entre chunks (default 200)
- `EMBEDDING_MODEL`: modelo OpenAI (default `text-embedding-3-small`)
- `OPENAI_API_KEY`: chave da API (opcional, ativa fallback mock se ausente)
- `DATABASE_URL`: string de conexao PostgreSQL

## Testes executados

### Suite completa: 58/58 passando

```
======================== 58 passed, 1 warning in 0.42s =========================
```

### Distribuicao por arquivo

| Arquivo de teste | Testes | Cobertura |
|---|---|---|
| `test_api_v1.py` | 6 | Health endpoints, stubs de documents/chat/summarize/compare |
| `test_contracts_v1.py` | 38 | Validacao, serializacao e roundtrip JSON de todos os schemas Pydantic |
| `test_process_document.py` | 14 | Pipeline completo, componentes unitarios, cenarios de erro |

### Cenarios testados em `test_process_document.py`

#### Endpoint com mocks completos
- `test_process_document_success`: pipeline completo (MinIO → extracao → chunking → embeddings → pgvector → status update) retorna 200 com `status=ready`.
- `test_process_document_file_not_found`: arquivo ausente no storage retorna 404.
- `test_process_document_storage_error`: falha de conexao com storage retorna 502.
- `test_process_document_invalid_pdf`: PDF corrompido retorna 400.

#### Testes unitarios de componentes
- `TestPDFExtractor`: extracao de PDF valido e rejeicao de arquivo invalido.
- `TestTextChunker`: chunking basico, texto vazio, multiplas paginas.
- `TestOpenAIEmbedder`: consistencia deterministica de embeddings mock e normalizacao unitaria.
- `TestPgVectorStore`: insercao com mock de DB e lista vazia retorna zero sem chamar conexao.

### Warning conhecido
- PyPDF2 emite `DeprecationWarning` recomendando migracao para `pypdf`. Nao afeta funcionalidade.

## Proximos passos

1. **Feature 1.2 - Integracao real Go → Python**: implementar chamada HTTP real do gateway Go para o endpoint de processamento de documentos no Python-Agent, com timeout configuravel, retry com backoff exponencial e circuit breaker.
2. Migrar PyPDF2 para `pypdf` (fork moderno sem warning de deprecacao).
3. Implementar processamento assincrono via fila para documentos grandes (evitar timeout do gateway).
4. Adicionar indice HNSW na coluna `embedding` do pgvector para busca vetorial otimizada em escala.
5. Implementar endpoint `GET /documents/{id}/status` para consulta assincrona de status de processamento.
