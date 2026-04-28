## ADDED Requirements

### Requirement: Processamento de documento para base vetorial
O sistema MUST expor `POST /process-document` no serviço Python/FastAPI para processar documento em chunking e gerar embeddings com persistência vetorial.

#### Scenario: Processamento bem-sucedido
- **WHEN** uma requisição válida de processamento de documento for recebida
- **THEN** o serviço realiza chunking, gera embeddings e persiste conteúdo e metadados no NeonDB/pgvector

#### Scenario: Documento inválido ou inacessível
- **WHEN** o documento não puder ser lido ou baixado
- **THEN** o serviço retorna erro estruturado com causa e status compatível

### Requirement: Chat RAG com rastreabilidade de fontes
O sistema MUST expor `POST /chat` retornando resposta e fontes utilizadas, incluindo no mínimo documento e página.

#### Scenario: Resposta com contexto suficiente
- **WHEN** houver contexto relevante recuperado na base vetorial
- **THEN** o serviço retorna resposta com lista de fontes rastreáveis

#### Scenario: Contexto insuficiente
- **WHEN** não houver contexto suficiente para responder com confiança
- **THEN** o serviço declara explicitamente limitação e evita afirmações sem fonte

### Requirement: Resumo estruturado de documento
O sistema MUST expor `POST /summarize-document` com saída estruturada contendo objetivo, metodologia, resultados e conclusão.

#### Scenario: Geração de resumo
- **WHEN** uma requisição válida de resumo for recebida
- **THEN** o serviço retorna resumo estruturado nos campos definidos

### Requirement: Comparação entre documentos
O sistema MUST expor `POST /compare-documents` para comparar múltiplos documentos por tema e retornar saída estruturada.

#### Scenario: Comparação entre N documentos
- **WHEN** a requisição informar tema e conjunto de documentos válidos
- **THEN** o serviço retorna comparação estruturada destacando convergências e divergências

### Requirement: Memória de sessão do agente
O sistema MUST persistir memória de sessão para conversas no backend Python usando armazenamento em PostgreSQL (NeonDB).

#### Scenario: Continuidade de sessão
- **WHEN** uma mensagem de chat incluir `session_id` existente
- **THEN** o serviço reutiliza contexto de memória previamente persistido
