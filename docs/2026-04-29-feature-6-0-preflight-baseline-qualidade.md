# Feature 6.0 - Preflight e baseline de qualidade

## Contexto
Feature de preparacao da Fase 6 para garantir medicao reproduzivel de qualidade tecnica e academica.

## Decisoes tecnicas
- Congelar baseline antes de qualquer ajuste de hardening.
- Versionar dataset e configuracoes de avaliacao.
- Registrar metas tecnicas e academicas em tabela unica.

## Metricas de baseline

| Metrica | Valor | Metodo de Medicao |
|---|---|---|
| Chat RAG latency (p50) | TBD | `scripts/benchmark/chat_latency.py` |
| Chat RAG latency (p95) | TBD | `scripts/benchmark/chat_latency.py` |
| Chat RAG latency (p99) | TBD | `scripts/benchmark/chat_latency.py` |
| Throughput (req/s) | TBD | `scripts/benchmark/load_test.py` |
| Error rate | TBD | Contagem de HTTP 5xx / total |
| Test coverage (Python) | TBD | `pytest --cov=app --cov-report=term` |
| Test coverage (Go) | TBD | `go test ./... -cover` |

## SLOs definidos

| SLO | Target | Prioridade |
|---|---|---|
| Chat RAG latency p95 | < 5s | Critica |
| Process document latency | < 60s | Alta |
| Gateway availability | > 99.5% | Critica |
| Test coverage Python | >= 70% | Alta |
| Test coverage Go | >= 60% | Alta |
| RAG context precision | >= 0.7 | Academica |
| RAG answer faithfulness | >= 0.75 | Academica |

## Golden dataset

- Localizacao: `services/python-agent/docs/evaluation/golden-dataset-v1.0.json`
- Versao: 1.0
- Modelo de embedding: `text-embedding-3-small`
- Seed: 42
- Total de perguntas: 6
- Projetos cobertos: test-project-1, test-project-2, test-project-3

### Schema do golden dataset

```json
{
  "version": "string — versao do dataset (ex: \"1.0\")",
  "seed": "number — seed para reprodutibilidade",
  "model": "string — modelo de embedding utilizado",
  "description": "string — descricao do dataset",
  "questions": [
    {
      "id": "string — identificador unico da pergunta (ex: \"q1\")",
      "project_id": "string — UUID do projeto vinculado",
      "question": "string — texto da pergunta em PT-BR",
      "expected_context_ids": ["string[] — IDs dos chunks esperados como contexto"],
      "reference_answer": "string — resposta de referencia para avaliacao"
    }
  ]
}
```

### Campos obrigatorios por pergunta

| Campo | Tipo | Descricao |
|---|---|---|
| `id` | string | Identificador unico (ex: "q1", "q2") |
| `project_id` | string | Projeto ao qual a pergunta se refere |
| `question` | string | Texto da pergunta |
| `expected_context_ids` | string[] | Chunks relevantes para responder |
| `reference_answer` | string | Resposta esperada (gold standard) |

## Implementacao
- Scripts de baseline em `scripts/benchmark/`.
- Definicao de SLOs nesta documentacao.
- Golden dataset versionado em `docs/evaluation/`.
- Testes de integracao com DB real em `tests/test_integration_db.py`.

## Testes executados
Nao aplicavel nesta etapa de documentacao. Execucao sera registrada durante implementacao da feature.

## Proximos passos
1. Criar scripts de baseline em `scripts/benchmark/`.
2. Publicar relatorio inicial de p50/p95/p99 e error rate.
3. Executar avaliacao RAG com golden dataset (Feature 6.4).
4. Consolidar resultados no quality gate (Feature 6.6).
