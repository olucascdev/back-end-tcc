## REMOVED Requirements

### Requirement: Pipeline de indexação de fontes públicas
**Reason**: Replaced by on-demand retrieval. Mass indexing consumes unnecessary resources for a TCC project.
**Migration**: Scheduled pipeline is disabled; on-demand adapter in python-agent handles retrieval per query.

### Requirement: Catálogo público em MongoDB
**Reason**: No longer needed. Public sources are queried in real-time rather than cached in MongoDB.
**Migration**: MongoDB collection `books` can be dropped after migration.

### Requirement: Armazenamento de artefatos em MinIO/S3
**Reason**: Public artifacts are no longer persisted. Only 3-5 items are downloaded transiently per query.
**Migration**: MinIO bucket `tcc-public-index` can be emptied after migration.

### Requirement: Embeddings públicos no NeonDB/pgvector
**Reason**: Public embeddings are generated on-demand and cached in Redis (1h TTL), not persisted in NeonDB.
**Migration**: Existing public embeddings in NeonDB can be removed.

### Requirement: Idempotência e reprocessamento seguro
**Reason**: No longer applicable without persistent pipeline and storage.
**Migration**: Not needed for on-demand model.

### Requirement: Agendamento e lock distribuído
**Reason**: No scheduled pipeline exists in the new model.
**Migration**: Redis lock logic can be removed from public-indexer.

### Requirement: Observabilidade operacional do pipeline
**Reason**: Pipeline no longer exists. Metrics will be replaced by on-demand retrieval metrics.
**Migration**: New metrics for on-demand retrieval will be added in python-agent.

## ADDED Requirements

### Requirement: Serviço public-indexer como stub administrativo
O sistema MUST manter o serviço public-indexer operacional como stub com endpoints de saúde e administrativos mínimos, sem execução de pipeline.

#### Scenario: Health check operacional
- **WHEN** uma requisição GET for feita para `/health`
- **THEN** o serviço responde com status simplificado (sem verificação de pipeline)

#### Scenario: Endpoint admin desabilitado
- **WHEN** uma requisição POST for feita para `/admin/index/run`
- **THEN** o serviço retorna 503 com mensagem indicando que indexação em massa foi descontinuada

## MODIFIED Requirements

### Requirement: Bootstrap do serviço public-indexer
O sistema MUST prover o serviço `public-indexer` como aplicação Python executável com arquitetura em camadas e endpoints de saúde, sem pipeline ativo.

#### Scenario: Health check com dependências reduzidas
- **WHEN** uma requisição GET for feita para `/health`
- **THEN** o serviço responde com status de saúde de MongoDB, PostgreSQL, MinIO e Redis (para compatibilidade), mas não inicia pipeline

#### Scenario: Estrutura em camadas
- **WHEN** o serviço for inicializado
- **THEN** o código está organizado em camadas `api`, `application`, `domain`, `infrastructure` e `core`, sem workers de indexação
