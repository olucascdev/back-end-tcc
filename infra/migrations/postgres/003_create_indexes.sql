-- =============================================================================
-- Migration 003: Create Indexes
-- =============================================================================
-- Indices para chaves estrangeiras e campos de busca frequente.
-- Melhora performance de JOINs, filtros e ordenacoes comuns.
-- =============================================================================

-- -------------------------------------------------------------------------
-- Indices para chaves estrangeiras (FKs)
-- -------------------------------------------------------------------------

-- projects.user_id — busca projetos por usuario
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);

-- documents.project_id — busca documentos por projeto
CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);

-- documents.status — filtro por status de processamento
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);

-- conversations.project_id — busca conversas por projeto
CREATE INDEX IF NOT EXISTS idx_conversations_project_id ON conversations(project_id);

-- conversations.session_id — busca conversas por sessao
CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id);

-- agent_sessions.project_id — busca sessoes de agente por projeto
CREATE INDEX IF NOT EXISTS idx_agent_sessions_project_id ON agent_sessions(project_id);

-- -------------------------------------------------------------------------
-- Indices para campos de busca frequente
-- -------------------------------------------------------------------------

-- users.email — login e lookup por email (ja tem UNIQUE, mas indice explicito)
-- Nao necessario criar — UNIQUE ja cria indice implicito

-- projects.title — busca por titulo de projeto (busca parcial por texto)
CREATE INDEX IF NOT EXISTS idx_projects_title ON projects USING GIN (to_tsvector('portuguese', title));

-- documents.filename — busca por nome de arquivo
CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename);

-- documents.created_at — ordenacao cronologica de documentos
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);

-- conversations.created_at — ordenacao cronologica de mensagens
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC);

-- agent_sessions.session_id — ja tem UNIQUE, indice implicito existe

-- -------------------------------------------------------------------------
-- Indice composto: documents por projeto + status (consulta comum de fila)
-- -------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_documents_project_status
    ON documents(project_id, status);

-- -------------------------------------------------------------------------
-- Indice composto: conversations por projeto + sessao + data
-- -------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_conversations_project_session_created
    ON conversations(project_id, session_id, created_at DESC);
