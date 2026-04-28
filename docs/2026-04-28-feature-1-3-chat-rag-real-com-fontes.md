# Feature 1.3 - Chat RAG real com fontes

## Contexto

Apos implementar o pipeline de processamento de documentos (Feature 1.1) e a integracao real Go → Python (Feature 1.2), o sistema possuia chunks e embeddings persistidos no pgvector, mas o endpoint de chat ainda operava em modo stub — retornando resposta mock sem consultar a base de conhecimento vetorial.

Sem RAG real, o sistema nao conseguia:
- responder perguntas com base no conteudo dos documentos processados
- citar fontes rastreaveis (documento, pagina, secao, score)
- evitar alucinacoes quando o contexto e insuficiente
- manter historico de conversas por sessao

Esta feature resolve:
- implementar pipeline RAG completo no Python-Agent
- embedding da query do usuario via OpenAI API
- busca similar no pgvector com filtro obrigatorio por `project_id`
- montagem de contexto estruturado a partir dos chunks recuperados
- chamada LLM com prompt do sistema + contexto + historico de sessao
- extracao de fontes citadas para resposta rastreavel
- fallback mock para desenvolvimento sem dependencia externa
- cobrir todo o pipeline com testes unitarios e de integracao

## Decisoes tecnicas

### Embedding da query

- Usa `OpenAIEmbedder.embed_query()` — mesmo embedder do pipeline de ingestao, garantindo que query e documentos compartilham espaco vetorial.
- Modelo `text-embedding-3-small` (dimensao 1536) via OpenAI API.
- **Fallback mock**: quando `OPENAI_API_KEY` nao esta configurada, gera embedding deterministico via hash MD5 do texto + vetor gaussiano normalizado. Permite desenvolvimento e testes sem dependencia externa.
- Embeddings mock sao consistentes (mesmo texto → mesmo vetor) e unitarios (norma = 1), compativeis com busca por distancia no pgvector.

### Busca similar com filtro `project_id`

- Metodo `PgVectorStore.search_similar_by_project()` adicionado ao store existente.
- Usa operador `<->` (distancia L2) do pgvector com filtro `WHERE metadata->>'project_id' = %s`.
- **Filtro por `project_id` obrigatorio**: evita contaminacao de contexto entre projetos diferentes — chunks de um projeto nunca aparecem na resposta de outro.
- **Threshold de relevancia**: `MIN_RELEVANCE_SCORE = 0.7` — chunks com score abaixo sao descartados. Score calculado como `1.0 - distance` (conversao de distancia L2 para similaridade).
- `top_k=5` como default — equilibrio entre contexto suficiente e limite de tokens do LLM.
- Resultados ordenados por score descendente (mais relevante primeiro).

### Montagem de contexto

- Metodo `_build_context()` formata cada chunk com metadata estruturado:
  ```
  [Fonte 1] Documento: <document_id>, Pagina: <page_number>
  Conteudo: <chunk_text>

  [Fonte 2] Documento: <document_id>, Pagina: <page_number>
  Conteudo: <chunk_text>
  ```
- Formato explicito permite ao LLM identificar origem de cada informacao e citar corretamente.
- Chunks separados por duplo newline para clareza visual no prompt.

### Chamada LLM

- Metodo `_call_llm()` monta mensagens para a API OpenAI:
  1. `system` — prompt do sistema definido em `Settings.SYSTEM_PROMPT`.
  2. `history` — ultimas 6 mensagens do historico de sessao (3 trocas user/assistant), excluindo a mensagem atual do usuario.
  3. `user` — pergunta do usuario prefixada com contexto dos documentos.
- **Limitacao de historico**: ultimas 6 mensagens para nao estourar limite de tokens.
- Parametros: `temperature=0.3` (respostas deterministicas), `max_tokens=1024`.
- **Fallback mock**: quando `OPENAI_API_KEY` ausente, gera resposta simulada baseada no primeiro chunk do contexto.
- Erros na API OpenAI capturados e relancados como `LLMError` com mensagem descritiva.

### Extracao de fontes

- Metodo `_extract_sources()` converte chunks recuperados em lista de objetos `Source`:
  - `document`: `document_id` do metadata.
  - `page`: `page_number` do metadata.
  - `section`: campo opcional do metadata (pode ser `null`).
  - `score`: similaridade arredondada para 4 casas decimais.
- Fontes incluidas na resposta `ChatResponse` para rastreabilidade completa.
- Quando sem contexto relevante, `sources` retorna lista vazia.

### Historico de sessao em memoria

- Classe `SessionHistory` armazena mensagens por `session_id` em dicionario em memoria.
- Cada chamada ao RAG salva mensagem do usuario e resposta do assistant.
- Historico usado para enriquecer contexto em chamadas subsequentes da mesma sessao.
- **Nota**: implementacao em memoria e temporaria — substituicao por Redis ou banco planejada na Feature 1.4.

### Resposta sem contexto relevante

- Quando busca vetorial retorna zero chunks acima do threshold, retorna mensagem padrao:
  > "Nao encontrei informacoes suficientes nos documentos do projeto para responder sua pergunta. Tente reformular ou consulte documentos diferentes."
- `sources` retorna lista vazia.
- Evita alucinacao: LLM nao e chamado quando contexto e insuficiente.

## Implementacao

### Pipeline completo de RAG

```
POST /api/v1/chat (ChatRequest)
  │
  ├─ 1. Salva mensagem do usuario no historico da sessao
  │     session_history.add_message(session_id, "user", message)
  │
  ├─ 2. Gera embedding da pergunta
  │     embedder.embed_query(message) → query_embedding[1536]
  │
  ├─ 3. Busca chunks similares no pgvector
  │     vector_store.search_similar_by_project(
  │       project_id, query_embedding, top_k=5, min_score=0.7
  │     ) → chunks[{content, metadata, score}]
  │
  ├─ 4. Se chunks vazios → retorna limitacao explicita
  │     ChatResponse(answer=NO_CONTEXT_ANSWER, sources=[], session_id)
  │
  ├─ 5. Monta contexto a partir dos chunks
  │     _build_context(chunks) → formatted_context_string
  │
  ├─ 6. Chama LLM com sistema + historico + contexto + pergunta
  │     _call_llm(context, question, session_id) → answer
  │
  ├─ 7. Extrai fontes dos chunks
  │     _extract_sources(chunks) → list[Source]
  │
  ├─ 8. Salva resposta no historico da sessao
  │     session_history.add_message(session_id, "assistant", answer)
  │
  └─ Response (ChatResponse)
        {answer, sources[{document, page, section?, score}], session_id, created_at}
```

### Arquivos implementados

#### `app/domain/rag_service.py` (novo)
- Pacote `domain` — camada de dominio para orquestracao de negocio.
- Classe `RAGService` com metodo principal `chat(project_id, session_id, message)`.
- Orquestra fluxo completo: embedding → busca → contexto → LLM → fontes.
- Classe `SessionHistory` para armazenamento em memoria de historico por sessao.
- Classe `LLMError` para erros durante chamada ao LLM.
- Constantes: `MIN_RELEVANCE_SCORE = 0.7`, `NO_CONTEXT_ANSWER`.
- Metodos privados:
  - `_build_context(chunks)` — formata chunks em string de contexto.
  - `_call_llm(context, question, session_id)` — chama OpenAI API ou fallback mock.
  - `_mock_llm_response(context, question)` — gera resposta simulada para desenvolvimento.
  - `_extract_sources(chunks)` — extrai lista de `Source` dos chunks.

#### `app/api/v1/endpoints/chat.py` (modificado)
- Endpoint `POST /api/v1/chat` com `response_model=ChatResponse`.
- Injecao de dependencia via FastAPI `Depends`: `Settings` → `RAGService`.
- Logging estruturado com `project_id`, `session_id`, `request_id`.
- Tratamento de erro:
  - `LLMError` → `502 Bad Gateway` com mensagem segura.
  - `Exception` generico → `500 Internal Server Error`.

#### `app/infrastructure/database/pgvector_store.py` (modificado)
- Metodo `search_similar_by_project(project_id, query_embedding, top_k, min_score)` adicionado.
- Busca com filtro `project_id` no metadata JSONB.
- Filtro pos-query por `min_score` para descartar resultados irrelevantes.
- Retorna lista de dicts com `content`, `metadata`, `score`.

#### `app/schemas/contracts_v1.py` (existente, referencia)
- `ChatRequest`: `project_id` (UUID), `session_id` (str), `message` (str), `filters` (opcional).
- `ChatResponse`: `answer` (str), `sources` (list[Source]), `session_id` (str), `created_at` (datetime).
- `Source`: `document` (str), `page` (int), `section` (str | null), `score` (float).

### Configuracion

Parametros configuraveis via `Settings` (Pydantic Settings):
- `OPENAI_API_KEY`: chave da API (opcional, ativa fallback mock se ausente)
- `OPENAI_MODEL`: modelo LLM (default `gpt-4o-mini`)
- `SYSTEM_PROMPT`: prompt do sistema para o LLM
- `DATABASE_URL`: string de conexao PostgreSQL

## Testes executados

### Suite completa: 72/72 passando

```
======================== 72 passed, 1 warning in 0.74s =========================
```

### Distribuicao por arquivo

| Arquivo de teste | Testes | Cobertura |
|---|---|---|
| `test_api_v1.py` | 6 | Health endpoints, stubs de documents/summarize/compare |
| `test_contracts_v1.py` | 38 | Validacao, serializacao e roundtrip JSON de todos os schemas Pydantic |
| `test_process_document.py` | 14 | Pipeline completo de processamento, componentes unitarios, cenarios de erro |
| `test_chat_rag.py` | 14 | RAGService com/sem contexto, formato de fontes, erro LLM, endpoint API, embedder query, pgvector search |

### Cenarios testados em `test_chat_rag.py`

#### RAGService com contexto relevante
- `test_chat_returns_answer_with_sources`: chat com chunks mock retorna resposta nao vazia, 3 fontes com score > 0.7, session_id preservado. Verifica chamadas ao embedder e vector store.
- `test_chat_preserves_session_history`: duas chamadas consecutivas na mesma sessao preservam historico (4 mensagens: 2 user + 2 assistant).

#### RAGService sem contexto relevante
- `test_chat_returns_limitation_when_no_chunks`: busca retorna lista vazia → resposta com `NO_CONTEXT_ANSWER` e sources vazia.
- `test_chat_returns_limitation_when_low_score`: chunks com score abaixo do threshold → mesma limitacao explicita.

#### Formato de fontes
- `test_sources_have_correct_format`: verifica campos `document`, `page`, `section`, `score` com valores corretos.

#### Erro do LLM
- `test_llm_error_raises_llm_error`: forca uso real do LLM (`_use_mock=False`), mock da OpenAI API retorna excecao → `LLMError` com mensagem "Falha ao gerar resposta".

#### Endpoint da API
- `test_chat_endpoint_returns_response_with_sources`: payload valido retorna 200 com answer, 1 source, session_id.
- `test_chat_endpoint_returns_limitation_without_context`: RAGService retorna limitacao → endpoint propaga com "Nao encontrei informacoes suficientes".
- `test_chat_endpoint_handles_llm_error`: `LLMError` no service → endpoint retorna 502 com detail.
- `test_chat_endpoint_validation_error`: payload com `project_id` invalido e campos vazios → 422.

#### Embedder query
- `test_embed_query_mock_returns_vector`: embedding mock retorna vetor de 1536 dimensoes.
- `test_embed_query_mock_consistent`: mesmo texto retorna mesmo embedding (deterministico).

#### PgVectorStore search
- `test_search_filters_by_min_score`: 3 rows retornadas (2 acima, 1 abaixo do threshold) → resultado filtra para 2 chunks com score >= 0.7.
- `test_search_empty_results`: fetchall retorna lista vazia → metodo retorna `[]`.

### Warning conhecido
- PyPDF2 emite `DeprecationWarning` recomendando migracao para `pypdf`. Nao afeta funcionalidade.

## Proximos passos

1. **Feature 1.4 - Persistencia de sessao e historico**: substituir `SessionHistory` em memoria por persistencia em Redis ou banco de dados. Persistir interacoes em tabela `conversations`. Reutilizar contexto por `session_id` entre reinicializacoes do servico.
2. Implementar summarize real de documentos (`POST /documents/summarize`).
3. Implementar comparacao tematica entre documentos (`POST /documents/compare`).
4. Adicionar indice HNSW na coluna `embedding` do pgvector para busca vetorial otimizada em escala.
5. Migrar PyPDF2 para `pypdf` (fork moderno sem warning de deprecacao).
