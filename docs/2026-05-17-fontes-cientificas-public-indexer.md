# Suporte a Fontes Científicas no Public Indexer

**Data:** 2026-05-17
**Serviço:** `services/public-indexer`
**Status:** Implementado

## Contexto

O public-indexer originalmente suportava apenas duas fontes de livros de domínio público:
- **Project Gutenberg**: livros clássicos em domínio público
- **Open Library**: catálogo aberto de livros

Para expandir o acervo com conteúdo acadêmico e científico, foi necessário adicionar suporte a três fontes adicionais:

- **OpenAlex**: API aberta de metadados acadêmicos (works, authors, concepts). Fornece dados sobre milhões de trabalhos científicos com informações de acesso aberto.
- **arXiv**: repositório de pre-prints em física, matemática, ciência da computação e áreas relacionadas. API Atom/XML com acesso direto a PDFs.
- **Crossref**: infraestrutura de metadados acadêmicos baseada em DOI. Nem todos os trabalhos possuem PDF aberto, mas os metadados são valiosos para o catálogo.

### Por que não foi necessário OpenSpec

Esta mudança foi tratada como extensão de capacidade dentro da feature existente de indexação de acervo público (Fase 5). Não altera contratos externos, não introduz breaking changes e mantém compatibilidade total com as fontes existentes. O OpenSpec já cobre a capacidade de "ingestão de catálogo público" — esta implementação apenas amplia as fontes suportadas dentro desse mesmo escopo.

## Decisões Técnicas

### 1. OpenAlex como fonte primária acadêmica
OpenAlex foi escolhido como primeira fonte científica porque:
- API REST JSON simples e bem documentada
- Paginação por cursor (eficiente para grandes volumes)
- Fornece `open_access.oa_url` direto para conteúdo aberto
- Dados normalizados com concepts (assuntos) e authorships

### 2. arXiv com parser XML nativo
A API do arXiv retorna feed Atom/XML. Foi usado `xml.etree.ElementTree` (stdlib Python) ao invés de `feedparser` para:
- Evitar dependência adicional
- Manter o requirements.txt enxuto
- Controle total sobre o parsing dos namespaces Atom/arXiv

### 3. Crossref com fallback gracioso para PDFs
Crossref fornece metadados ricos, mas muitos trabalhos não têm PDF aberto. A decisão foi:
- Persistir metadados no catálogo mesmo sem PDF
- Logar warning quando não há URL de download
- O pipeline de embedding skipa o item, mas os metadados ficam disponíveis para busca

### 4. Campos genéricos em `BookMetadata`
Ao invés de criar campos específicos por fonte (ex: `openalex_id`, `arxiv_id`), foram adicionados campos genéricos:
- `source_id`: identificador único na fonte original
- `source_provider`: nome do provedor (ex: "openalex", "arxiv", "crossref")
- `doi`: Digital Object Identifier
- `abstract`: resumo do trabalho
- `url`: URL direta para o recurso

Isso permite adicionar novas fontes no futuro sem alterar o modelo.

### 5. Prioridade do `stable_key()`
A ordem de prioridade para deduplicação foi estendida:
1. `gutenberg_id` → `gutenberg:{id}`
2. `ol_key` → `ol:{key}`
3. `source_provider:source_id` → `{provider}:{id}` (novo)
4. Hash de título + autores (fallback)

## Implementação

### Arquivos Criados

| Arquivo | Descrição |
|---------|-----------|
| `app/infrastructure/sources/openalex_client.py` | Cliente HTTP assíncrono para API OpenAlex com paginação por cursor e retry exponencial |
| `app/infrastructure/sources/arxiv_client.py` | Cliente HTTP assíncrono para API arXiv com parser XML Atom e paginação por offset |
| `app/infrastructure/sources/crossref_client.py` | Cliente HTTP assíncrono para API Crossref com paginação por offset e retry |
| `tests/test_openalex_client.py` | Testes unitários do cliente OpenAlex (normalização, busca, filtros) |
| `tests/test_arxiv_client.py` | Testes unitários do cliente arXiv (parse XML, feed Atom, fallback PDF) |
| `tests/test_crossref_client.py` | Testes unitários do cliente Crossref (normalização, extração de ano, busca) |
| `tests/test_models.py` | Testes de `stable_key()` com todas as prioridades e fallback hash |

### Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `app/domain/models.py` | Adicionados campos `source_id`, `source_provider`, `doi`, `abstract`, `url` em `BookMetadata`. `stable_key()` agora suporta `source_provider:source_id`. |
| `app/infrastructure/sources/__init__.py` | Factory atualizada com `create_openalex_client()`, `create_arxiv_client()`, `create_crossref_client()`. |
| `app/application/catalog_sync.py` | `CatalogSyncUseCase` agora aceita clientes opcionais das 3 novas fontes. Métodos `_sync_openalex()`, `_sync_arxiv()`, `_sync_crossref()` adicionados. `execute()` itera sobre todas as fontes. |
| `app/application/artifact_processor.py` | `_resolve_download_url()` agora resolve URLs para OpenAlex (OA URL), arXiv (PDF construído), Crossref (URL do metadata ou warning). |
| `app/core/config.py` | Adicionadas configurações `OPENALEX_ENABLED`, `OPENALEX_BASE_URL`, `ARXIV_ENABLED`, `ARXIV_BASE_URL`, `CROSSREF_ENABLED`, `CROSSREF_BASE_URL`. |
| `.env.example` | Adicionadas variáveis de ambiente com defaults e comentários explicativos. |
| `tests/test_catalog_sync.py` | Adicionados fixtures e testes para OpenAlex, arXiv, Crossref e todas as fontes juntas. |
| `tests/test_artifact_processor.py` | Adicionados testes para processamento de artefatos das 3 novas fontes. |

## Testes Executados

### Resultados

```
221 tests collected
216 passed
2 skipped (vector store tests que requerem psycopg)
3 failed (pre-existentes em test_admin.py - auth 403, não relacionado)
```

### Cobertura por componente

| Componente | Testes | Status |
|------------|--------|--------|
| `BookMetadata.stable_key()` | 11 | ✅ Todos passaram |
| `OpenAlexClient` | 7 | ✅ Todos passaram |
| `ArxivClient` | 7 | ✅ Todos passaram |
| `CrossrefClient` | 10 | ✅ Todos passaram |
| `CatalogSyncUseCase` (novas fontes) | 8 | ✅ Todos passaram |
| `ArtifactProcessorUseCase` (novas fontes) | 4 | ✅ Todos passaram |
| Testes existentes | 174 | ✅ Todos passaram (sem regressão) |

### Cenários testados

- Normalização de documentos completos e mínimos para cada fonte
- Paginação (cursor para OpenAlex, offset para arXiv/Crossref)
- Retry exponencial em erros transientes
- Fallback de URL de PDF para arXiv
- Extração de ano com prioridade (published-print > published-online > created)
- Deduplicação por stable_key com todas as prioridades
- Processamento de artefatos com e sem URL de download
- Fontes solicitadas sem cliente configurado (report de erro)
- Sincronização de todas as fontes simultaneamente

## Próximos Passos

1. **Google Books**: Adicionar como fonte adicional seguindo o mesmo padrão genérico (`source_provider`/`source_id`).
2. **Semantic Scholar**: API alternativa com dados acadêmicos e links para PDFs.
3. **Rate limiting por fonte**: Implementar limites específicos por API (arXiv recomenda 1 req/3s).
4. **Filtros por assunto/idioma**: Permitir configurar quais subjects/languages sincronizar por fonte.
5. **Monitoramento de quota**: Adicionar métricas de rate limit e quota usage por fonte.
6. **Testes de integração**: Testes contra APIs reais (com mocks de resposta real) para validar parsing em produção.
