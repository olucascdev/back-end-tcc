## ADDED Requirements

### Requirement: Benchmark endpoints for load testing
O sistema MUST expor endpoints administrativos no gateway Go para iniciar, acompanhar e reportar benchmark de carga, medindo latência p50/p95/p99, throughput e taxa de erro.

#### Scenario: Início de benchmark de carga
- **WHEN** um usuário admin autenticado chama `POST /benchmark/load` com parâmetros de concorrência e duração
- **THEN** o gateway inicia workers concorrentes, direciona requisições ao agente Python e coleta métricas em tempo real

#### Scenario: Consulta de resultado de benchmark
- **WHEN** um usuário admin autenticado chama `GET /benchmark/load/{run_id}`
- **THEN** o gateway retorna relatório estruturado com latência p50/p95/p99, throughput, taxa de erro e timestamp de início/fim

#### Scenario: Proteção de endpoint admin
- **WHEN** um usuário sem scope `admin` tenta acessar endpoints de benchmark
- **THEN** o gateway retorna status 403 sem iniciar benchmark

### Requirement: Resilience behavior under dependency failure
O sistema MUST demonstrar comportamento de resiliência mensurável quando dependências (agente Python, NeonDB, Redis) estiverem degradadas ou indisponíveis, com fallback controlado ou erro elegante.

#### Scenario: Degradação do agente Python
- **WHEN** o agente Python apresentar alta latência ou falhas e o circuit breaker atingir limiar
- **THEN** o gateway abre o circuito, retorna erro elegante e registra métrica de degradação

#### Scenario: Degradação do NeonDB
- **WHEN** o NeonDB estiver indisponível durante requisição de chat
- **THEN** o gateway retorna erro 503 com mensagem padronizada e não acumula conexões fantasmas

#### Scenario: Degradação do Redis
- **WHEN** o Redis estiver indisponível e uma requisição de chat for recebida
- **THEN** o gateway ignora cache semântico, encaminha ao agente Python e registra miss forçado

#### Scenario: Recuperação de dependência
- **WHEN** uma dependência degradada retornar a saúde após intervalo de recuperação
- **THEN** o gateway detecta recuperação, fecha circuito se aplicável e retoma operação normal
