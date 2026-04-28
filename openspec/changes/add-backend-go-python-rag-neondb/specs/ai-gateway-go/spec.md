## ADDED Requirements

### Requirement: Rate limiting por usuário no gateway Go
O sistema MUST aplicar rate limiting por usuário no gateway Go/Gin para proteger os serviços internos e manter previsibilidade de consumo.

#### Scenario: Requisição dentro do limite
- **WHEN** um usuário autenticado envia requisições abaixo do limite configurado
- **THEN** o gateway permite o processamento e encaminha a requisição

#### Scenario: Requisição excede limite
- **WHEN** um usuário autenticado excede o limite da janela temporal
- **THEN** o gateway retorna status de limitação com mensagem padronizada

### Requirement: Cache semântico por projeto
O sistema MUST usar cache semântico em Redis para respostas de chat por projeto, reduzindo chamadas repetidas ao agente Python.

#### Scenario: Pergunta semanticamente equivalente
- **WHEN** uma pergunta no mesmo projeto for equivalente a uma pergunta previamente respondida
- **THEN** o gateway retorna resposta do cache sem chamar o agente Python

#### Scenario: Pergunta inédita
- **WHEN** não houver entrada semanticamente equivalente no cache
- **THEN** o gateway chama o agente Python e persiste a resposta no cache

### Requirement: Fila concorrente de processamento de PDFs
O sistema MUST processar documentos em fila concorrente no gateway Go usando workers para escalar ingestão sem bloquear requisições de chat.

#### Scenario: Novo documento enfileirado
- **WHEN** um documento for enviado para processamento
- **THEN** o gateway registra job, enfileira tarefa e inicia execução por worker disponível

#### Scenario: Processamento concluído
- **WHEN** o worker concluir processamento com sucesso
- **THEN** o gateway envia webhook de conclusão ao BFF com status e metadados mínimos

### Requirement: Circuit breaker para dependência Python
O sistema MUST aplicar circuit breaker nas chamadas ao agente Python para degradar de forma controlada em caso de indisponibilidade.

#### Scenario: Falhas consecutivas na dependência
- **WHEN** o número de falhas consecutivas atingir o limiar configurado
- **THEN** o circuito abre e o gateway retorna erro elegante sem tentar chamada remota

#### Scenario: Recuperação da dependência
- **WHEN** o intervalo de recuperação expirar e a chamada de teste for bem-sucedida
- **THEN** o circuito fecha e o gateway retoma chamadas normais ao agente Python
