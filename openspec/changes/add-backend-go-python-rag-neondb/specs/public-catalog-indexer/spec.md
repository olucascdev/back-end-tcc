## ADDED Requirements

### Requirement: Pipeline de indexação de fontes públicas
O sistema MUST executar pipeline agendado para ingestão de fontes públicas acadêmicas/literárias e geração de embeddings reutilizáveis no RAG.

#### Scenario: Execução completa de ciclo
- **WHEN** o agendamento iniciar um ciclo de indexação
- **THEN** o pipeline busca metadados, baixa artefatos, processa embeddings e conclui atualização de status

### Requirement: Catálogo público em MongoDB
O sistema MUST persistir metadados de catálogo público em MongoDB na coleção `books`.

#### Scenario: Livro novo encontrado
- **WHEN** um item novo for encontrado nas fontes públicas
- **THEN** o pipeline persiste metadados no MongoDB com status `indexed=false`

#### Scenario: Livro indexado com sucesso
- **WHEN** o processamento vetorial for concluído
- **THEN** o pipeline atualiza o item no MongoDB com `indexed=true` e `indexed_at`

### Requirement: Armazenamento de artefatos em MinIO/S3
O sistema MUST persistir artefatos baixados (PDF/TXT) em MinIO/S3 para rastreabilidade e reprocessamento.

#### Scenario: Download concluído
- **WHEN** um arquivo de fonte pública for baixado
- **THEN** o artefato é armazenado em bucket e sua referência é persistida no catálogo

### Requirement: Embeddings públicos no NeonDB/pgvector
O sistema MUST persistir embeddings de acervo público no NeonDB com marcação de origem.

#### Scenario: Persistência vetorial de item público
- **WHEN** o conteúdo de um livro público for processado
- **THEN** os embeddings são persistidos com `source_type=public_library`

### Requirement: Idempotência e reprocessamento seguro
O sistema MUST evitar duplicidade de indexação e suportar reprocessamento controlado.

#### Scenario: Item já indexado
- **WHEN** o pipeline identificar item já indexado e sem alteração relevante
- **THEN** o item é ignorado sem duplicar embeddings
