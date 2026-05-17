## ADDED Requirements

### Requirement: Semantic cache implementation on chat path
The system SHALL implement Redis-based semantic cache on the chat request path in the Go gateway. When a chat request arrives, the gateway MUST check the cache before calling the Python agent. On cache hit, the cached response (answer + sources) MUST be returned immediately. On cache miss, the Python agent MUST be called and the response stored in cache with a configurable TTL.

#### Scenario: Cache hit returns stored response
- **WHEN** a chat request arrives with a query semantically equivalent to a previously cached query in the same project
- **THEN** the gateway returns the cached response without calling the Python agent and includes header `X-Cache: HIT`

#### Scenario: Cache miss calls Python agent
- **WHEN** a chat request arrives with no semantically equivalent entry in cache
- **THEN** the gateway calls the Python agent, stores the response in cache with configured TTL, and returns the response with header `X-Cache: MISS`

#### Scenario: Redis unavailable falls back to agent
- **WHEN** Redis is unreachable during a cache lookup
- **THEN** the gateway bypasses cache, calls the Python agent directly, and logs the cache error without failing the request

#### Scenario: Cache timeout does not block request
- **WHEN** the cache lookup exceeds the configured timeout (default 50ms)
- **THEN** the gateway treats it as a cache miss, calls the Python agent, and logs the timeout

### Requirement: Cache invalidation by document version
The system SHALL invalidate semantic cache entries for a project when any document in that project is updated or reprocessed. Cache keys MUST include the project's document version so that version increment naturally invalidates old entries.

#### Scenario: Document update invalidates project cache
- **WHEN** a document in a project is reprocessed and its version increments
- **THEN** all subsequent cache lookups for that project use the new version key, making old entries inaccessible

#### Scenario: Cache isolation between projects
- **WHEN** a document in project A is updated
- **THEN** cache entries for project B remain valid and unaffected

### Requirement: Cache observability metrics
The system SHALL expose Prometheus metrics for semantic cache operations including hit/miss counters, latency histogram, and error counter with appropriate labels.

#### Scenario: Cache hit increments counter
- **WHEN** a cache hit occurs
- **THEN** the `cache_hits_total` counter is incremented with the `project_id` label

#### Scenario: Cache miss increments counter
- **WHEN** a cache miss occurs
- **THEN** the `cache_misses_total` counter is incremented with the `project_id` label

#### Scenario: Cache latency is recorded
- **WHEN** a cache lookup completes (hit or miss)
- **THEN** the `cache_latency_seconds` histogram records the duration

#### Scenario: Cache error is tracked
- **WHEN** a cache operation fails (Redis unavailable, timeout, serialization error)
- **THEN** the `cache_errors_total` counter is incremented with an `error_type` label

### Requirement: Cache decision logging
The system SHALL log structured cache decision events with cache status, project ID, and latency for every chat request that passes through the cache layer.

#### Scenario: Log cache hit event
- **WHEN** a cache hit occurs
- **THEN** a structured log entry is emitted with fields `cache_status=hit`, `project_id`, and `latency_ms`

#### Scenario: Log cache miss event
- **WHEN** a cache miss occurs
- **THEN** a structured log entry is emitted with fields `cache_status=miss`, `project_id`, and `reason`

## MODIFIED Requirements

### Requirement: Cache semântico por projeto
O sistema MUST usar cache semantico em Redis para respostas de chat por projeto, reduzindo chamadas repetidas ao agente Python. O cache MUST incluir versionamento de documento para invalidacao automatica e expor metricas de hit/miss ratio. O cache MUST ter fallback transparente para o agente Python quando Redis estiver indisponivel.

#### Scenario: Pergunta semanticamente equivalente
- **WHEN** uma pergunta no mesmo projeto for equivalente a uma pergunta previamente respondida e a versao do documento nao mudou
- **THEN** o gateway retorna resposta do cache sem chamar o agente Python e registra metrica de hit

#### Scenario: Pergunta inédita
- **WHEN** nao houver entrada semanticamente equivalente no cache
- **THEN** o gateway chama o agente Python, persiste a resposta no cache com TTL configuravel, e registra metrica de miss

#### Scenario: Documento atualizado invalida cache
- **WHEN** um documento do projeto e reprocessado e a versao incrementa
- **THEN** entradas de cache anteriores tornam-se inacessiveis e novas queries geram miss ate repovoar o cache
