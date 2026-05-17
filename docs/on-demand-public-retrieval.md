# On-Demand Public Source Retrieval

## Contexto
O sistema anterior realizava indexacao em massa de ~100 livros do OpenAlex via pipeline agendado (public-indexer), consumindo storage (MinIO), banco de dados (MongoDB) e embeddings persistentes (NeonDB/pgvector) para um TCC. Essa abordagem era over-engineered: livros eram baixados e processados independentemente de serem consultados.

## Decisao Tecnica
Substituir a indexacao em massa por busca sob demanda (on-demand):
- O agente busca 3-5 referencias relevantes **apenas quando o usuario pergunta**
- Nao ha persistencia de artefatos publicos (MinIO/MongoDB/Postgres vetorial)
- Texto e baixado, chunking e embedding sao feitos em tempo real
- Cadeia de fallback garante cobertura mesmo quando a fonte principal nao tem download

## Implementacao

### Fontes e Fallback
1. **OpenAlex API** (primaria): busca works academicos por query, retorna metadata + URL de acesso aberto
2. **Unpaywall API** (fallback 1): usa DOI para encontrar PDF open access
3. **Google Books API** (fallback 2): busca preview/link para livros sem acesso aberto

### Modulos Criados
- `app/infrastructure/sources/openalex_client.py` — cliente OpenAlex
- `app/infrastructure/sources/unpaywall_client.py` — cliente Unpaywall
- `app/infrastructure/sources/google_books_client.py` — cliente Google Books
- `app/domain/retrieval/public_source_retriever.py` — orquestrador do fallback chain

### Integracao no Chat
- `RAGService.chat()` agora chama `PublicSourceRetriever.retrieve()` quando `retrieval_mode="project_plus_public"`
- Chunks publicos sao mesclados com chunks do projeto e deduplicados
- Fontes publicas aparecem no array `sources` da resposta com `source_type="public_library"`

### Gateway
- Corrigido mapeamento de erros 404 do Python: antes retornava 400 generico, agora retorna 404 correto

## Testes Executados
- Import check de todos os novos modulos: ✅
- Build do gateway Go: ✅
- Teste manual de chat com `project_only`: ✅ (200 OK, resposta sem fontes publicas)
- Teste de chat com `project_plus_public`: pendente (requer restart do python-agent)

## Proximos Passos
- Testar end-to-end via gateway com `project_plus_public`
- Adicionar cache Redis de 1h para embeddings on-demand (otimizacao)
- Considerar remocao completa do servico public-indexer (atualmente stub)
- Adicionar testes unitarios para os clients de fonte
