## Contexto

Durante os testes end-to-end, dois problemas impediram o fluxo esperado:

1. O `go-gateway` retornava `400 invalid request: upstream validation failed` no endpoint de chat.
2. O `public-indexer` concluia jobs com `books_embedded=0` e alta taxa de falha em `artifact_download` para fonte OpenAlex.
3. O `public-indexer` falhava na etapa de embedding com `No module named 'psycopg.extras'`.

Adicionalmente, o job de indexacao com `source_filter=openalex` ainda processava registros de outros providers.

## Decisoes tecnicas

- Habilitar follow redirects no download de artefatos via `httpx`, pois várias URLs de OA/DOI retornam 301/302 antes do arquivo final.
- Aplicar `source_filter` diretamente na consulta de pendentes no MongoDB, para garantir isolamento por provider.
- Remover dependencia de `psycopg.extras` (nao disponivel em psycopg3) no bulk insert de embeddings.
- Ajustar default de `PYTHON_AGENT_URL` no gateway para incluir `/api/v1`, evitando erro quando variavel nao esta exportada.
- Manter o comportamento atual de retries e timeouts do indexer, mudando apenas a resolucao de redirects.

## Implementacao

### 1) Redirects no download de artefatos

- Arquivo: `services/public-indexer/app/infrastructure/artifact_storage.py`
- Mudança: `httpx.AsyncClient(..., follow_redirects=True)` no método `download_artifact`.

Impacto: reduz falhas por respostas 301/302 em URLs de OpenAlex/Crossref/DOI.

### 2) Filtro real de pendentes por provider

- Arquivo: `services/public-indexer/app/domain/services.py`
- Mudança: assinatura de `get_pending_books` para aceitar `source_filter: Optional[str]`.
- Mudança: query MongoDB passou a usar `{"indexed": False, "source_provider": <source_filter>}` quando filtro informado.

- Arquivo: `services/public-indexer/app/application/usecases.py`
- Mudança: `RunIndexUseCase.execute` agora repassa `source_filter` para `get_pending_books`.

Impacto: jobs com `source_filter=openalex` não processam registros de outros providers.

### 3) Compatibilidade psycopg3 no vector store

- Arquivo: `services/public-indexer/app/infrastructure/vector_store.py`
- Mudança: remoção de `from psycopg.extras import execute_values`.
- Mudança: uso de `cursor.executemany(...)` com cast `%s::vector`.
- Mudança: inclusão de helper `_to_vector_literal` para serializar embeddings para formato pgvector (`[v1,v2,...]`).

Impacto: elimina erro de import e permite inserção de embeddings no NeonDB.

### 4) Default seguro de URL do agente Python no gateway

- Arquivo: `services/go-gateway/internal/config/config.go`
- Mudança: default de `PYTHON_AGENT_URL` de `http://localhost:8000` para `http://localhost:8000/api/v1`.

- Arquivo: `services/go-gateway/.env.example`
- Mudança: exemplo atualizado para `http://python-agent:8000/api/v1`.

Impacto: evita `upstream validation failed` quando o gateway roda sem export de variaveis.

## Testes executados

- Health checks:
  - `GET /api/v1/health` no `go-gateway` -> `200`
  - `GET /api/v1/health` no `public-indexer` -> `200`
  - `GET /api/v1/health/ready` no `public-indexer` -> `200`
- Teste direto no `python-agent`:
  - `POST /api/v1/chat` -> `200`

Observacao: o `go-gateway` ainda retornou `400 upstream validation failed` durante teste sem reinicio confirmado do processo apos ajuste de `.env`.

## Proximos passos

1. Reiniciar `go-gateway` para carregar `PYTHON_AGENT_URL=http://localhost:8000/api/v1`.
2. Reiniciar `public-indexer` para garantir carga das mudanças de redirect/filtro.
3. Reexecutar:
   - `POST /api/v1/admin/catalog/sync` com `source_filter=openalex`
   - `POST /api/v1/admin/index/run` com `source_filter=openalex`
4. Validar em NeonDB se houve incremento em `document_embeddings` para `source_provider=openalex`.
