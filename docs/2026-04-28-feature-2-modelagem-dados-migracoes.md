# Feature 2 - Modelagem de Dados e Migracoes (Fase 0)

**Data:** 2026-04-28
**Status:** Implementado e testado

## Contexto

Implementacao da camada de dados do backend TCC, cobrindo:
- PostgreSQL (NeonDB) com extensao pgvector para embeddings
- MongoDB para catalogo publico de livros (Project Gutenberg + Open Library)
- Sistema de migracoes versionadas e aplicaveis via shell script e Makefile

## Decisoes Tecnicas

### PostgreSQL
- **UUID como PK padrao**: `uuid-ossp` extension para geracao automatica
- **pgvector com HNSW**: indice HNSW escolhido em vez de IVFFlat por melhor performance em buscas aproximadas (ANN) no pgvector moderno (v0.5.0+). Parametros: `m=16`, `ef_construction=64` — balance entre memoria e precisao
- **Dimensao 1536**: compativel com OpenAI `text-embedding-ada-002`
- **JSONB para campos flexiveis**: `metadata` em documents/embeddings, `sources` em conversations, `memory` em agent_sessions
- **Trigger `updated_at`**: atualizacao automatica de timestamp em todas as tabelas com campo `updated_at`
- **CHECK constraints**: validacao de enum para `status` (documents) e `role` (conversations)
- **Indices compostos**: `documents(project_id, status)` para consultas de fila de processamento; `conversations(project_id, session_id, created_at DESC)` para historico de conversas
- **Indice GIN em metadata**: permite consultas por qualquer chave dentro do JSONB
- **Indice B-tree em `metadata->>'project_id'`**: lookup direto de embeddings por projeto

### MongoDB
- **Schema validation com `moderate` level**: valida em insert e update, permite migracoes de dados existentes
- **Indices sparse + unique**: `gutenberg_id` e `ol_key` sao opcionais mas unicos quando presentes
- **Indice parcial**: `idx_books_unindexed_gutenberg` filtra apenas documentos com `indexed: false` — otimiza consulta de livros pendentes
- **Indice text**: busca full-text no titulo

### Migracoes
- **SQL idempotente**: `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS` — seguro re-executar
- **MongoDB idempotente**: drop + recreate da collection antes de criar
- **Shell script**: suporta flags `--postgres-only` e `--mongo-only`
- **Makefile**: targets `migrate-up`, `migrate-up-postgres`, `migrate-up-mongo`, `test-migrations`

## Implementacao

### Arquivos Criados

| Arquivo | Descricao |
|---------|-----------|
| `infra/migrations/postgres/001_create_base_tables.sql` | Tabelas: users, projects, documents, conversations, agent_sessions |
| `infra/migrations/postgres/002_create_embeddings_table.sql` | Tabela embeddings com indice HNSW vector(1536) |
| `infra/migrations/postgres/003_create_indexes.sql` | Indices para FKs, buscas frequentes e composicoes |
| `infra/migrations/mongodb/001_create_books_collection.js` | Collection books com validacao e indices |
| `infra/migrations/apply_migrations.sh` | Script de aplicacao de migracoes |
| `Makefile` | Targets para infra e migracoes |

### Schema PostgreSQL

```
users
├── id (UUID PK)
├── email (VARCHAR UNIQUE)
├── name (VARCHAR)
├── created_at (TIMESTAMPTZ)
└── updated_at (TIMESTAMPTZ)

projects
├── id (UUID PK)
├── user_id (UUID FK → users)
├── title (VARCHAR)
├── description (TEXT)
├── created_at (TIMESTAMPTZ)
└── updated_at (TIMESTAMPTZ)

documents
├── id (UUID PK)
├── project_id (UUID FK → projects)
├── filename (VARCHAR)
├── storage_key (VARCHAR)
├── status (pending|processing|ready|error)
├── page_count (INTEGER)
├── metadata (JSONB)
├── created_at (TIMESTAMPTZ)
└── updated_at (TIMESTAMPTZ)

conversations
├── id (UUID PK)
├── project_id (UUID FK → projects)
├── session_id (VARCHAR)
├── role (user|assistant)
├── content (TEXT)
├── sources (JSONB)
└── created_at (TIMESTAMPTZ)

agent_sessions
├── id (UUID PK)
├── project_id (UUID FK → projects)
├── session_id (VARCHAR UNIQUE)
├── memory (JSONB)
├── created_at (TIMESTAMPTZ)
└── updated_at (TIMESTAMPTZ)

embeddings
├── id (UUID PK)
├── content (TEXT)
├── embedding (vector(1536))
├── metadata (JSONB)
└── created_at (TIMESTAMPTZ)
```

### Schema MongoDB

```
books
├── title (string, required)
├── authors (string[])
├── isbn (string)
├── gutenberg_id (string, unique, sparse)
├── ol_key (string, unique, sparse)
├── formats (string[])
├── indexed (bool, required)
├── indexed_at (date)
└── metadata (object)
    ├── language (string)
    ├── subjects (string[])
    ├── publication_year (int)
    ├── publisher (string)
    └── description (string)
```

## Testes Executados

### Resultado: SUCESSO

**PostgreSQL:**
- 6 tabelas criadas: `users`, `projects`, `documents`, `conversations`, `agent_sessions`, `embeddings`
- 23 indices criados (incluindo HNSW vector, GIN metadata, FKs, compostos)
- Todas as migracoes aplicadas sem erro

**MongoDB:**
- Collection `books` criada com schema validation
- 7 indices criados: `_id_`, `idx_books_title_text`, `idx_books_authors`, `idx_books_indexed`, `idx_books_gutenberg_id`, `idx_books_ol_key`, `idx_books_unindexed_gutenberg`

### Comandos de teste
```bash
make test-migrations
# Sobe infra → aplica migracoes → verifica tabelas/indices → para containers
```

## Proximos Passos

1. Implementar servico Go de gestao de documentos (upload, status tracking)
2. Implementar servico Python de processamento de documentos (chunking, embedding)
3. Adicionar migracoes de seed data para testes
4. Implementar sistema de versionamento de migracoes (ex: `schema_migrations` table) para tracking de quais migracoes ja foram aplicadas
