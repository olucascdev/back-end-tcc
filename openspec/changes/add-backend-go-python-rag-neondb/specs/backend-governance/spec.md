## ADDED Requirements

### Requirement: Documentação por feature em português
O sistema MUST exigir criação de arquivo em `docs/*.md` para cada feature ou plano implementado, com conteúdo em português do Brasil.

#### Scenario: Feature concluída
- **WHEN** uma feature for implementada
- **THEN** existe arquivo dedicado em `docs/` descrevendo contexto, decisões, implementação, testes e próximos passos

### Requirement: Idioma de comentários no código
O sistema MUST manter comentários de código em português do Brasil quando comentários forem necessários.

#### Scenario: Inclusão de comentário técnico
- **WHEN** um comentário for adicionado para explicar bloco não óbvio
- **THEN** o comentário é escrito em português do Brasil

### Requirement: Convenção universal de commits
O sistema MUST adotar mensagens de commit em inglês seguindo convenção universal de commits (Conventional Commits).

#### Scenario: Novo commit de feature
- **WHEN** uma alteração de feature for versionada
- **THEN** a mensagem usa padrão como `feat:`, `fix:`, `refactor:`, `docs:` com descrição em inglês

### Requirement: Nomenclatura de código em inglês
O sistema MUST usar nomenclatura em inglês para variáveis, funções, classes, módulos e identificadores técnicos.

#### Scenario: Criação de nova função
- **WHEN** uma nova função for implementada
- **THEN** seu nome e parâmetros usam termos em inglês claros e consistentes

### Requirement: Boas práticas de backend e arquitetura limpa
O sistema MUST aplicar princípios de Clean Code e arquitetura em camadas com separação de responsabilidades.

#### Scenario: Implementação de endpoint
- **WHEN** um endpoint novo for adicionado
- **THEN** regras de negócio, acesso a dados e transporte HTTP permanecem desacoplados

### Requirement: Uso orientado de skills do OpenCode
O sistema MUST orientar o agente a identificar necessidades da tarefa e usar skills especializadas apropriadas.

#### Scenario: Tarefa focada em Go
- **WHEN** a atividade exigir implementação ou design relevante em Go
- **THEN** o agente utiliza skill `golang-pro` para orientar padrões e decisões

#### Scenario: Tarefa focada em FastAPI/Agno
- **WHEN** a atividade exigir implementação ou design relevante em Python/FastAPI
- **THEN** o agente utiliza skill `fastapi-expert` para orientar padrões e decisões
