# Feature 5.5 - Idempotencia, Retry e Agendamento

**Data:** 2026-04-29
**Status:** Implementado

## Contexto

O pipeline de indexacao publica depende de fontes externas instaveis e operacoes longas. E necessario garantir que falhas transientes nao corrompam o estado, que jobs duplicados nao rodem em paralelo e que falhas permanentes sejam rastreaveis para reprocessamento manual.

## Decisoes Tecnicas

### RetryPolicy

- Implementacao generica com backoff exponencial + jitter (decorrelacao).
- Configuravel: `max_retries`, `base_delay`, `max_delay`, `backoff_factor`, `jitter`.
- Retry condicional: so retenta em excecoes configuraveis (`httpx.HTTPStatusError`, `ConnectionError`).
- 4xx (exceto 429) nao sao retentados — falha rapida.
- Decorator `@retry` e funcao `retry_async` para uso explicito.

### IndexScheduler

- Agendador baseado em APScheduler com trigger `cron` (configuravel via env).
- Lock distribuido via Redis (`SET key NX EX ttl`) para evitar execucao duplicada em multiplas replicas.
- Heartbeat: atualiza chave Redis a cada N segundos durante execucao; se heartbeat parar, lock expira e outra replica assume.
- Dry-run mode: executa pipeline sem persistencia para validacao.

### FailureTracker (DLQ)

- Fila de morte em Redis (lista `dlq:indexer`) para jobs que esgotaram retries.
- Cada entrada contem: `job_id`, `stage`, `error`, `traceback`, `artifact_key`, `timestamp`, `retry_count`.
- Endpoint admin: `GET /admin/dlq` para listar; `POST /admin/dlq/retry/{job_id}` para reprocessar.
- Limite de tamanho: DLQ trunca apos 1000 entradas (FIFO) para evitar crescimento ilimitado.

## Implementacao

### Arquivos Criados/Modificados

| Arquivo | Acao | Descricao |
|---------|------|-----------|
| `app/infrastructure/retry.py` | Criado | RetryPolicy com backoff+jitter, decorator, retry condicional, configuravel |
| `app/infrastructure/scheduler.py` | Criado | IndexScheduler com APScheduler, lock Redis, heartbeat, dry-run |
| `app/infrastructure/dlq.py` | Criado | FailureTracker com DLQ em Redis, listagem, retry manual, limite de tamanho |
| `app/api/v1/endpoints/admin.py` | Modificado | Adicionados endpoints `/admin/dlq` e `/admin/dlq/retry/{job_id}` |
| `app/domain/models.py` | Modificado | Adicionados `DLQEntry`, `SchedulerConfig` |
| `app/core/config.py` | Modificado | Adicionadas variaveis `SCHEDULER_CRON`, `REDIS_LOCK_TTL`, `DLQ_MAX_SIZE` |
| `tests/test_retry.py` | Criado | 13 testes: sucesso, retry, backoff, jitter, max retries, nao retry 4xx, decorator, async |
| `tests/test_scheduler.py` | Criado | 10 testes: lock adquirido, lock recusado, heartbeat, dry-run, cron parse, execucao, liberacao lock |
| `tests/test_failure_tracker.py` | Criado | 8 testes: adicionar DLQ, listar, retry, limite tamanho, serializacao, erro inexistente, FIFO |

## Testes Executados

```
$ pytest services/public-indexer/tests/test_retry.py -v
13 passed in 0.33s

$ pytest services/public-indexer/tests/test_scheduler.py -v
10 passed in 0.51s

$ pytest services/public-indexer/tests/test_failure_tracker.py -v
8 passed in 0.29s

---
Total Feature 5.5: 31 passed
```

## Proximos Passos

- **Feature 5.6**: Observabilidade completa — metricas Prometheus, logs estruturados e relatorio de job.

## Riscos Residuais

- Lock Redis depende de clock skew minimo — em clusters geograficamente distribuidos, TTL deve ser conservador.
- DLQ em Redis e volatil — para producao critica, considerar persistencia em PostgreSQL.
