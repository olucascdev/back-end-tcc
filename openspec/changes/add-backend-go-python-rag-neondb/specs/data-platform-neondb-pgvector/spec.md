## ADDED Requirements

### Requirement: NeonDB serverless como banco principal
O sistema MUST utilizar NeonDB serverless como banco principal para dados relacionais do domínio e armazenamento vetorial com pgvector.

#### Scenario: Persistência de domínio
- **WHEN** operações de usuários, projetos, documentos e conversas forem executadas
- **THEN** os dados são persistidos no NeonDB em esquema relacional versionado

### Requirement: Estrutura vetorial unificada
O sistema MUST manter embeddings de documentos de usuário e biblioteca pública em estrutura vetorial consultável por similaridade.

#### Scenario: Busca por similaridade em projeto
- **WHEN** uma consulta semântica for executada para um projeto
- **THEN** a busca considera embeddings do escopo do projeto e retorna resultados ordenados por similaridade

#### Scenario: Busca por similaridade em biblioteca pública
- **WHEN** uma consulta semântica exigir acervo público
- **THEN** a busca considera embeddings marcados como `source_type=public_library`

### Requirement: Índices vetoriais e desempenho
O sistema MUST manter índices vetoriais adequados à estratégia de similaridade configurada.

#### Scenario: Índice vetorial disponível
- **WHEN** a base vetorial estiver operacional
- **THEN** os índices necessários para busca por similaridade permanecem aplicados e válidos

### Requirement: Migração de schema controlada
O sistema MUST aplicar migrações versionadas para evolução de schema sem perda de consistência.

#### Scenario: Nova versão de schema
- **WHEN** uma mudança de schema for promovida
- **THEN** ela é aplicada por migração versionada com possibilidade de rollback definido
