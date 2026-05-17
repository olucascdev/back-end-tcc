# Feature 5.2 - Ingestao de Catalogo Publico

**Data:** 2026-04-29
**Status:** Implementado

## Contexto

Apos o bootstrap do `public-indexer` (Feature 5.1), o proximo passo e ingerir metadados de acervos publicos. Fontes alvo:
- **Open Library** (API REST com paginacao)
- **Project Gutenberg** (catalogo RDF + espelhos de download)

Objetivo: obter metadados de livros (titulo, autores, idioma, assuntos), aplicar deduplicacao e persistir no MongoDB como catalogo unificado.

## Decisoes Tecnicas

### OpenLibrary Client

- Cliente `OpenLibraryClient` com `httpx.AsyncClient` e timeout configuravel.
- Paginacao via cursor (`offset`) com tamanho de pagina parametrizavel.
- Retry com backoff exponencial para rate limits (429).
- Normalizacao de resposta: mapeia campos OpenLibrary (`key`, `title`, `author_name`, `subject`, `language`) para `BookMetadata` interno.
- Tratamento de campos ausentes: `author_name` vazio vira lista vazia; `subject` ausente vira lista vazia.

### Gutenberg Client

- Cliente `GutenbergClient` consome espelho `gutenberg.org/files/` para texto puro.
- Catalogo obtido via `catalog.rdf` simplificado ou espelho de metadados em JSON.
- Parser defensivo de HTML/texto para extrair `title`, `author`, `language`, `subjects`.
- Download de artefato via stream com limite de tamanho (protecao contra arquivos muito grandes).

### CatalogSyncUseCase

- Orquestra a sincronizacao: busca nas fontes, deduplica, insere/atualiza no MongoDB.
- Chave de deduplicacao estavel: `gutenberg_id` > `ol_key` > `hash(title + authors)`.
- Upsert no MongoDB via `replace_one` com `upsert=True` na colecao `books`.
- Campos enriquecidos no documento MongoDB:
  - `source_provider`: `openlibrary` | `gutenberg`
  - `source_id`: ID original na fonte
  - `synced_at`: timestamp da ultima sincronizacao
  - `dedup_key`: chave estavel gerada

## Implementacao

### Arquivos Criados/Modificados

| Arquivo | Acao | Descricao |
|---------|------|-----------|
| `app/infrastructure/sources/open_library_client.py` | Criado | Cliente async OpenLibrary com paginacao, retry, mapeamento para BookMetadata |
| `app/infrastructure/sources/gutenberg_client.py` | Criado | Cliente Gutenberg com download stream, parser defensivo, limite de tamanho |
| `app/application/catalog_sync.py` | Criado | CatalogSyncUseCase com deduplicacao, upsert MongoDB, enriquecimento de metadados |
| `app/domain/models.py` | Modificado | Adicionados campos `source_provider`, `source_id`, `dedup_key`, `synced_at` em BookMetadata |
| `app/infrastructure/clients.py` | Modificado | Adicionado metodo `get_books_collection()` no MongoDBClient |
| `tests/test_open_library_client.py` | Criado | 7 testes: fetch, paginacao, retry 429, timeout, campos ausentes, parsing, erro HTTP |
| `tests/test_gutenberg_client.py` | Criado | 8 testes: download stream, parser, limite tamanho, catalogo, erro rede, mimetype, hash, retry |
| `tests/test_catalog_sync.py` | Criado | 7 testes: deduplicacao, upsert, merge metadados, filtro fonte, erro fonte, chave estavel, batch |

## Testes Executados

```
$ pytest services/public-indexer/tests/test_open_library_client.py -v
7 passed in 0.32s

$ pytest services/public-indexer/tests/test_gutenberg_client.py -v
8 passed in 0.41s

$ pytest services/public-indexer/tests/test_catalog_sync.py -v
7 passed in 0.28s

---
Total Feature 5.2: 22 passed
```

## Proximos Passos

- **Feature 5.3**: Armazenamento de artefatos (PDF/TXT) no MinIO/S3 com selecao de formato e checksum.
- **Feature 5.4**: Extracao de texto, chunking e geracao de embeddings para acervo publico.

## Riscos Residuais

- Parser Gutenberg depende de HTML/texto espelho — mudanca de layout do site pode quebrar extracao.
- OpenLibrary aplica rate limit nao documentado — monitorar 429 em producao.
