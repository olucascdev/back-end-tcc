-- =============================================================================
-- Migration 002: Create Embeddings Table
-- =============================================================================
-- Tabela para armazenar vetores de embeddings gerados pelo modelo de texto.
-- Usa pgvector com dimensao 1536 (compativel com OpenAI text-embedding-ada-002).
-- Indice HNSW escolhido por melhor performance em buscas近似 (ANN) no pgvector
-- moderno (v0.5.0+), suportando operacoes de distancia cosine, L2 e inner product.
-- =============================================================================

-- Extensao pgvector (necessaria para o tipo vector)
CREATE EXTENSION IF NOT EXISTS vector;

-- -------------------------------------------------------------------------
-- Tabela: embeddings
-- Vetores de embeddings extraidos de documentos processados
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS embeddings (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content     TEXT NOT NULL,
    embedding   vector(1536) NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- Indice vetorial HNSW
-- Operacao: cosine distance (<=>) — mais adequado para embeddings de texto
-- Parametros: m=16 (balance entre memoria e precisao), ef_construction=64
-- -------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_embeddings_embedding
    ON embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- -------------------------------------------------------------------------
-- Indices para campos de busca dentro do JSONB metadata
-- -------------------------------------------------------------------------

-- Indice B-tree no campo project_id extraido do JSONB (consultas diretas)
CREATE INDEX IF NOT EXISTS idx_embeddings_project_id
    ON embeddings ((metadata->>'project_id'));

-- Indice GIN simples para consultas por qualquer chave no metadata
CREATE INDEX IF NOT EXISTS idx_embeddings_metadata_gin
    ON embeddings USING GIN (metadata);
