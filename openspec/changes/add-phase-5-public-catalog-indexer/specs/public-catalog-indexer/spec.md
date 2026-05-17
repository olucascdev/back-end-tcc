## MODIFIED Requirements

### Requirement: Pipeline de indexação de fontes públicas
O sistema MUST executar pipeline agendado para ingestão de fontes públicas acadêmicas/literárias e geração de embeddings reutilizáveis no RAG, expondo endpoints administrativos para controle manual e acompanhamento.

#### Scenario: Execução completa de ciclo agendado
- **WHEN** o agendamento iniciar um ciclo de indexação
- **THEN** o pipeline busca metadados, baixa artefatos, processa embeddings e conclui atualização de status

#### Scenario: Execução manual via endpoint administrativo
- **WHEN** uma requisição POST for feita para `/admin/index/run`
- **THEN** o pipeline inicia um novo job de indexação e retorna o `job_id`

#### Scenario: Consulta de status de job
- **WHEN** uma requisição GET for feita para `/admin/index/jobs/{job_id}`
- **THEN** o sistema retorna o status atual do job, incluindo estágio, itens processados e falhas

### Requirement: Catálogo público em MongoDB
O sistema MUST persistir metadados de catálogo público em MongoDB na coleção `books`, com deduplicação previsível e controle de estado de indexação.

#### Scenario: Livro novo encontrado
- **WHEN** um item novo for encontrado nas fontes públicas
- **THEN** o pipeline persiste metadados no MongoDB com status `indexed=false`

#### Scenario: Livro alterado detectado
- **WHEN** um item existente tiver metadados ou conteúdo alterado
- **THEN** o pipeline atualiza o documento e redefine `indexed=false` para reprocessamento

#### Scenario: Livro indexado com sucesso
- **WHEN** o processamento vetorial for concluído
- **THEN** o pipeline atualiza o item no MongoDB com `indexed=true` e `indexed_at`

#### Scenario: Deduplicação por chave estável
- **WHEN** o pipeline processar um item com `gutenberg_id`, `ol_key` ou hash fallback já existente
- **THEN** o item é tratado como atualização em vez de inserção

### Requirement: Armazenamento de artefatos em MinIO/S3
O sistema MUST persistir artefatos baixados em MinIO/S3 para rastreabilidade e reprocessamento, aplicando seleção de formato e controle de integridade.

#### Scenario: Download concluído com formato preferencial
- **WHEN** um arquivo de fonte pública for baixado
- **THEN** o artefato é armazenado em bucket com chave determinística `provider/source_id/version`

#### Scenario: Seleção de formato por prioridade
- **WHEN** múltiplos formatos estiverem disponíveis para um item
- **THEN** o sistema seleciona o melhor formato pela ordem de prioridade configurável (padrão: txt > epub > pdf)

#### Scenario: Verificação de integridade
- **WHEN** um artefato for baixado com sucesso
- **THEN** o sistema calcula e persiste o `checksum` do conteúdo e atualiza o catálogo com `artifact_key`

### Requirement: Embeddings públicos no NeonDB/pgvector
O sistema MUST persistir embeddings de acervo público no NeonDB com marcação de origem completa, suportando chunking e processamento em lote.

#### Scenario: Persistência vetorial de item público
- **WHEN** o conteúdo de um livro público for processado
- **THEN** os embeddings são persistidos com `source_type=public_library`

#### Scenario: Chunking e geração em lote
- **WHEN** o texto de um artefato for extraído
- **THEN** o sistema aplica chunking com parâmetros configuráveis e gera embeddings em lote antes da persistência

#### Scenario: Metadados obrigatórios de origem
- **WHEN** um embedding público for persistido
- **THEN** os metadados MUST incluir `source_type=public_library`, `source_provider`, `source_id`, `artifact_key` e `checksum`

### Requirement: Idempotência e reprocessamento seguro
O sistema MUST evitar duplicidade de indexação e suportar reprocessamento controlado, usando fingerprint de conteúdo e retry seguro.

#### Scenario: Item já indexado sem alteração
- **WHEN** o pipeline identificar item já indexado e sem alteração relevante
- **THEN** o item é ignorado sem duplicar embeddings

#### Scenario: Reprocessamento por mudança de conteúdo
- **WHEN** o checksum de um item já indexado for diferente do anterior
- **THEN** o sistema gera novos embeddings com `chunk_version` atualizada e remove embeddings anteriores do mesmo `source_id`

#### Scenario: Retry em falha transiente
- **WHEN** uma operação de storage ou fonte falhar com erro transiente
- **THEN** o sistema aplica retry com backoff exponencial e jitter até o limite configurado

## ADDED Requirements

### Requirement: Bootstrap do serviço public-indexer
O sistema MUST prover o serviço `public-indexer` como aplicação Python executável com arquitetura em camadas e endpoints de saúde.

#### Scenario: Health check com dependências
- **WHEN** uma requisição GET for feita para `/health`
- **THEN** o serviço responde com status de saúde de MongoDB, PostgreSQL, MinIO e Redis

#### Scenario: Estrutura em camadas
- **WHEN** o serviço for inicializado
- **THEN** o código está organizado em camadas `api`, `application`, `domain`, `infrastructure` e `core`

### Requirement: Agendamento e lock distribuído
O sistema MUST executar o pipeline de indexação de forma agendada e prevenir execuções concorrentes usando lock distribuído via Redis.

#### Scenario: Execução periódica configurável
- **WHEN** o intervalo configurado em `SYNC_INTERVAL_MINUTES` for atingido
- **THEN** o pipeline inicia automaticamente um novo ciclo de indexação

#### Scenario: Prevenção de concorrência por lock
- **WHEN** um ciclo de indexação já estiver em execução e outro for disparado
- **THEN** o segundo ciclo é bloqueado pelo lock Redis e abortado com log informativo

#### Scenario: Liberação de lock após conclusão
- **WHEN** um job de indexação concluir ou falhar fatalmente
- **THEN** o lock distribuído é liberado para permitir nova execução

### Requirement: Observabilidade operacional do pipeline
O sistema MUST expor métricas e logs estruturados para auditoria, diagnóstico e governança do pipeline de indexação.

#### Scenario: Métricas expostas
- **WHEN** o serviço estiver operacional
- **THEN** as métricas `public_indexer_runs_total`, `public_indexer_run_duration_seconds`, `public_books_fetched_total`, `public_books_indexed_total` e `public_indexer_failures_total` MUST estar disponíveis para coleta

#### Scenario: Logs estruturados por item
- **WHEN** um item for processado pelo pipeline
- **THEN** cada estágio gera log estruturado contendo `request_id`, `job_id`, `source_provider`, `source_id` e `stage`

#### Scenario: Relatório de fim de job
- **WHEN** um job de indexação concluir
- **THEN** o sistema emite relatório com totais de novos, atualizados, ignorados, indexados e falhos
