# Feature 5.6 - Observabilidade e Operacao

**Data:** 2026-04-29
**Status:** Implementado

## Contexto

Com o pipeline funcional, e necessario visibilidade completa do que o indexador esta fazendo: metricas quantitativas, logs estruturados rastreaveis e relatorios de fim de job. Isso permite operacao em producao e deteccao rapida de anomalias.

## Decisoes Tecnicas

### Metricas Prometheus

6 metricas customizadas expostas em `/metrics`:

| Metrica | Tipo | Descricao |
|---------|------|-----------|
| `indexer_jobs_total` | Counter | Total de jobs iniciados (labels: `source_provider`, `status`) |
| `indexer_artifacts_downloaded_bytes` | Counter | Bytes baixados por fonte |
| `indexer_embeddings_generated_total` | Counter | Total de embeddings gerados |
| `indexer_stage_duration_seconds` | Histogram | Duracao por stage (download, extract, chunk, embed, store) |
| `indexer_dlq_entries_total` | Counter | Entradas na DLQ |
| `indexer_active_jobs` | Gauge | Jobs em execucao no momento |

Todas as metricas usam `prometheus_client` com registrador isolado para evitar conflito com outras apps.

### Structured Logging

- Todos os logs em JSON com campos obrigatorios:
  - `timestamp`, `level`, `message`
  - `job_id`, `source_id`, `stage` (contexto operacional)
  - `duration_ms`, `error` (quando aplicavel)
- Logger propagado via `contextvars` para manter `job_id` em corrotinas concorrentes.
- Nivel INFO para operacao normal; DEBUG habilitavel via env.

### JobReporter

- `JobReporter` gera relatorio ao final de cada job:
  - `job_id`, `status` (`completed` | `failed` | `partial`)
  - `stages`: lista com duracao e contagem por stage
  - `totals`: livros processados, artefatos baixados, embeddings gerados, chunks criados
  - `errors`: lista de erros (se houver)
  - `dlq_count`: entradas na fila de morte
- Relatorio persistido no `JobStore` e retornado no endpoint `GET /admin/index/jobs/{job_id}`.

## Implementacao

### Arquivos Criados/Modificados

| Arquivo | Acao | Descricao |
|---------|------|-----------|
| `app/core/metrics.py` | Criado | 6 metricas Prometheus com labels, registrador isolado, helper functions |
| `app/application/job_reporter.py` | Criado | JobReporter com relatorio estruturado, agregacao de stages, persistencia no JobStore |
| `app/core/logging.py` | Modificado | Adicionados contextvars para `job_id`/`source_id`/`stage`, formato JSON padronizado |
| `app/application/usecases.py` | Modificado | Instrumentado com metrics e logging em cada stage do pipeline |
| `app/api/v1/endpoints/admin.py` | Modificado | Endpoint `GET /admin/index/jobs/{job_id}` retorna relatorio completo |
| `tests/test_metrics.py` | Criado | 11 testes: contagem, histograma, gauge, labels, isolamento, tipo, incremento, observacao |
| `tests/test_job_reporter.py` | Criado | 7 testes: relatorio completo, parcial, falha, stages, totais, persistencia, serializacao |

## Testes Executados

```
$ pytest services/public-indexer/tests/test_metrics.py -v
11 passed in 0.27s

$ pytest services/public-indexer/tests/test_job_reporter.py -v
7 passed in 0.31s

---
Total Feature 5.6: 18 passed
```

## Proximos Passos

- Integrar public-indexer ao docker-compose do projeto.
- Consumir embeddings publicos no chat RAG (fase futura).
- Persistir JobStore em PostgreSQL ou Redis para sobreviver a restarts.
- Hardening de producao: TLS no MinIO, autenticacao no scheduler admin.

## Riscos Residuais

- Metricas em memoria sao perdidas em restart — Prometheus scraping deve ser frequente.
- Logs JSON aumentam volume de disco — policy de rotacao necessaria.
