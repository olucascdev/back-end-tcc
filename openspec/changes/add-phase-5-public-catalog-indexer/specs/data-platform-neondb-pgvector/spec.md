## MODIFIED Requirements

### Requirement: Estrutura vetorial unificada
O sistema MUST manter embeddings de documentos de usuário e biblioteca pública em estrutura vetorial consultável por similaridade, com schema unificado e metadados de origem obrigatórios.

#### Scenario: Busca por similaridade em projeto
- **WHEN** uma consulta semântica for executada para um projeto
- **THEN** a busca considera embeddings do escopo do projeto e retorna resultados ordenados por similaridade

#### Scenario: Busca por similaridade em biblioteca pública
- **WHEN** uma consulta semântica exigir acervo público
- **THEN** a busca considera embeddings marcados como `source_type=public_library`

#### Scenario: Schema unificado de embeddings
- **WHEN** um embedding for persistido no NeonDB
- **THEN** ele é armazenado na tabela unificada `document_embeddings` com colunas `id`, `embedding`, `metadata` (JSONB), `source_type`, `source_provider`, `source_id`, `artifact_key`, `checksum`, `chunk_version`, `created_at`

#### Scenario: Pipeline bloqueia metadata incompleta
- **WHEN** o pipeline público tentar persistir embedding sem `source_type`, `source_provider`, `source_id`, `artifact_key` ou `checksum`
- **THEN** a operação é rejeitada antes de atingir o banco

### Requirement: Índices vetoriais e desempenho
O sistema MUST manter índices vetoriais adequados à estratégia de similaridade configurada e índices de filtragem por origem.

#### Scenario: Índice vetorial disponível
- **WHEN** a base vetorial estiver operacional
- **THEN** os índices necessários para busca por similaridade permanecem aplicados e válidos

#### Scenario: Índice para filtragem por source_type
- **WHEN** consultas filtrarem por `source_type=public_library` ou `source_type=user_document`
- **THEN** o banco utiliza índice adequado em `source_type` para evitar scan sequencial

## ADDED Requirements

### Requirement: Resolução de nome de tabela vetorial
O sistema MUST resolver a divergência de nomenclatura entre runtime e migrações, padronizando em `document_embeddings` como nome oficial da tabela unificada.

#### Scenario: Migração padroniza nome da tabela
- **WHEN** a migração de schema for aplicada
- **THEN** a tabela vetorial unificada é criada ou renomeada para `document_embeddings` e a migração anterior que usava `embeddings` é corrigida ou complementada

#### Scenario: Runtime alinha com schema
- **WHEN** o serviço public-indexer ou python-agent persistir embeddings
- **THEN** a escrita ocorre na tabela `document_embeddings` conforme contrato unificado
