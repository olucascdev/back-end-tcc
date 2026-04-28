# Change: Estruturar backend poliglota para assistente acadêmico com RAG

## Why
O projeto precisa formalizar, via SDD, uma arquitetura de backend escalável para processamento de documentos acadêmicos, chat com RAG e indexação pública de acervo. Sem especificações explícitas, a implementação tende a ficar inconsistente entre serviços e sem critérios de aceite claros.

## What Changes
- Definir capability de gateway de IA em Go/Gin com rate limiting, cache semântico, fila concorrente de PDFs e circuit breaker.
- Definir capability do agente RAG em Python/FastAPI com Agno para processamento de documentos, chat com fontes, resumo e comparação.
- Definir capability de dados com NeonDB serverless (domínio principal e embeddings via pgvector).
- Definir capability do indexador público em Python com MongoDB para catálogo e MinIO/S3 para artefatos.
- Definir capability de governança de backend com padrões de documentação, idioma de comentários, convenção de commits e nomenclatura.

## Impact
- Affected specs:
  - `ai-gateway-go`
  - `rag-agent-python`
  - `data-platform-neondb-pgvector`
  - `public-catalog-indexer`
  - `backend-governance`
- Affected code:
  - `services/go-gateway/*`
  - `services/python-agent/*`
  - `services/public-indexer/*`
  - `infra/database/*`
  - `docs/*`
