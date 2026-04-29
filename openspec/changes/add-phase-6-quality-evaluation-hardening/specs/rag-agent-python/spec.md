## ADDED Requirements

### Requirement: Public library retrieval mode in chat RAG
O sistema MUST suportar modo de recuperação `project_plus_public` no chat RAG, combinando documentos do projeto com acervo público indexado, controlado por feature flag.

#### Scenario: Modo project_plus_public ativado
- **WHEN** uma requisição de chat informar `retrieval_mode=project_plus_public` e a feature flag `ENABLE_PUBLIC_RETRIEVAL` estiver ativa
- **THEN** o serviço recupera chunks do projeto e do acervo público, ordenados por similaridade, e inclui `source_type` em cada fonte

#### Scenario: Modo project_only padrão
- **WHEN** uma requisição de chat não informar `retrieval_mode` ou informar `project_only`
- **THEN** o serviço recupera apenas chunks do projeto, preservando comportamento existente

#### Scenario: Feature flag desabilitada
- **WHEN** `ENABLE_PUBLIC_RETRIEVAL=false` e uma requisição solicitar `project_plus_public`
- **THEN** o serviço retorna erro indicando modo não disponível

### Requirement: RAG evaluation pipeline with academic metrics
O sistema MUST fornecer pipeline reprodutível de avaliação RAG que calcule faithfulness, answer relevancy, context precision e context recall sobre golden dataset versionado.

#### Scenario: Execução do pipeline
- **WHEN** o script de evaluation for executado apontando para um golden dataset versionado
- **THEN** o sistema gera embeddings e respostas com seed e modelo fixos, computa as quatro métricas e exporta resultado estruturado

#### Scenario: Reprodutibilidade garantida
- **WHEN** o mesmo golden dataset e configuração forem reexecutados
- **THEN** os scores das métricas permanecem deterministicamente iguais dentro de margem numérica esperada

#### Scenario: Exportação de resultados
- **WHEN** a avaliação completar com sucesso
- **THEN** o sistema persiste resultados em JSON/CSV e gera sumário executivo com médias por métrica

## MODIFIED Requirements

### Requirement: Chat RAG com rastreabilidade de fontes
O sistema MUST expor `POST /chat` retornando resposta e fontes utilizadas, incluindo no mínimo documento, página e `source_type`. O request MUST aceitar campo opcional `retrieval_mode` com valores `project_only` (default) ou `project_plus_public`.

#### Scenario: Resposta com contexto suficiente
- **WHEN** houver contexto relevante recuperado na base vetorial
- **THEN** o serviço retorna resposta com lista de fontes rastreáveis contendo `source_type`

#### Scenario: Contexto insuficiente
- **WHEN** não houver contexto suficiente para responder com confiança
- **THEN** o serviço declara explicitamente limitação e evita afirmações sem fonte

#### Scenario: Modo de recuperação project_plus_public
- **WHEN** o request incluir `retrieval_mode=project_plus_public` e a feature flag estiver habilitada
- **THEN** o serviço inclui fontes de `source_type=public_library` e `source_type=project_document` na resposta

#### Scenario: Modo de recuperação project_only padrão
- **WHEN** o request omitir `retrieval_mode`
- **THEN** o serviço recupera apenas `source_type=project_document` e retorna fontes correspondentes
