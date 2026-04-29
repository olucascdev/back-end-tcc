-- =============================================================================
-- Migration 004: Unify Embeddings Table Name
-- =============================================================================
-- Resolve divergencia de nomenclatura entre migracao 002 (tabela 'embeddings')
-- e runtime python-agent (tabela 'document_embeddings').
--
-- Estrategia:
--   1. Se 'embeddings' existe e 'document_embeddings' nao existe → renomeia
--   2. Se nenhuma existe → cria 'document_embeddings'
--   3. Se ambas existem → migra dados de 'embeddings' para 'document_embeddings'
--      e renomeia indices
--   4. Preserva todos os dados existentes
--
-- Down migration: rever renomeacao ou remover tabela criada.
-- =============================================================================

-- Extensao pgvector (garante disponibilidade)
CREATE EXTENSION IF NOT EXISTS vector;

-- -------------------------------------------------------------------------
-- Up: unifica para document_embeddings
-- -------------------------------------------------------------------------

DO $$
BEGIN
    -- Caso 1: 'embeddings' existe e 'document_embeddings' nao existe → renomeia
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'embeddings')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'document_embeddings') THEN

        -- Renomeia tabela
        ALTER TABLE embeddings RENAME TO document_embeddings;

        -- Renomeia indices existentes
        ALTER INDEX IF EXISTS idx_embeddings_embedding
            RENAME TO idx_document_embeddings_embedding;
        ALTER INDEX IF EXISTS idx_embeddings_project_id
            RENAME TO idx_document_embeddings_project_id;
        ALTER INDEX IF EXISTS idx_embeddings_metadata_gin
            RENAME TO idx_document_embeddings_metadata_gin;

        RAISE NOTICE 'Tabela embeddings renomeada para document_embeddings';

    -- Caso 2: nenhuma existe → cria do zero
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'embeddings')
          AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'document_embeddings') THEN

        CREATE TABLE document_embeddings (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            content     TEXT NOT NULL,
            embedding   vector(1536) NOT NULL,
            metadata    JSONB NOT NULL DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        -- Indice vetorial HNSW
        CREATE INDEX idx_document_embeddings_embedding
            ON document_embeddings
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);

        -- Indices para campos de busca dentro do JSONB metadata
        CREATE INDEX idx_document_embeddings_project_id
            ON document_embeddings ((metadata->>'project_id'));

        CREATE INDEX idx_document_embeddings_metadata_gin
            ON document_embeddings USING GIN (metadata);

        RAISE NOTICE 'Tabela document_embeddings criada do zero';

    -- Caso 3: ambas existem → migra dados e remove duplicata
    ELSIF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'embeddings')
          AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'document_embeddings') THEN

        -- Migra registros que nao existem em document_embeddings (por id)
        INSERT INTO document_embeddings (id, content, embedding, metadata, created_at)
        SELECT e.id, e.content, e.embedding, e.metadata, e.created_at
        FROM embeddings e
        WHERE NOT EXISTS (
            SELECT 1 FROM document_embeddings d WHERE d.id = e.id
        );

        -- Renomeia indices da tabela embeddings para evitar conflito de nome
        ALTER INDEX IF EXISTS idx_embeddings_embedding
            RENAME TO idx_embeddings_embedding_old;
        ALTER INDEX IF EXISTS idx_embeddings_project_id
            RENAME TO idx_embeddings_project_id_old;
        ALTER INDEX IF EXISTS idx_embeddings_metadata_gin
            RENAME TO idx_embeddings_metadata_gin_old;

        -- Remove tabela antiga apos migracao
        DROP TABLE embeddings;

        RAISE NOTICE 'Dados de embeddings migrados para document_embeddings; tabela antiga removida';

    ELSE
        -- document_embeddings ja existe sozinha → nada a fazer
        RAISE NOTICE 'Tabela document_embeddings ja existe; nenhuma acao necessaria';
    END IF;
END $$;

-- -------------------------------------------------------------------------
-- Down: rever para estado anterior (embeddings)
-- -------------------------------------------------------------------------
-- NOTA: Executar apenas se necessario. Em producao, preferir manter
-- document_embeddings como nome oficial.

-- DO $$
-- BEGIN
--     IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'document_embeddings')
--        AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'embeddings') THEN
--
--         ALTER TABLE document_embeddings RENAME TO embeddings;
--
--         ALTER INDEX IF EXISTS idx_document_embeddings_embedding
--             RENAME TO idx_embeddings_embedding;
--         ALTER INDEX IF EXISTS idx_document_embeddings_project_id
--             RENAME TO idx_embeddings_project_id;
--         ALTER INDEX IF EXISTS idx_document_embeddings_metadata_gin
--             RENAME TO idx_embeddings_metadata_gin;
--
--         RAISE NOTICE 'Tabela document_embeddings renomeada de volta para embeddings';
--     END IF;
-- END $$;
