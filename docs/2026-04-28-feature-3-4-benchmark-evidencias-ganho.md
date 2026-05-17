# Feature 3.4 — Benchmark e Evidencias de Ganho de Performance do Cache

**Data:** 2026-04-28
**Status:** Implementado
**Responsavel:** Equipe de desenvolvimento

---

## Contexto

A Feature 3.1 implementou cache semantico com Redis para o endpoint de chat RAG, prometendo reducao significativa de latencia e carga no agente Python. Esta feature (3.4) tem como objetivo **provar empiricamente** que o cache entrega os ganhos prometidos, gerando evidencias comparativas reproduziveis.

### Problema

Sem benchmark comparativo, nao e possivel:
- Quantificar a reducao de latencia (p50/p95/p99) com cache ativo
- Medir a reducao de chamadas ao agente Python
- Validar se o hit ratio atinge as metas estabelecidas (>=40%)
- Tomar decisoes baseadas em dados sobre tuning de cache (TTL, tamanho, estrategia)

### Solucao

Criar infraestrutura de benchmark que compara automaticamente dois cenarios:
1. **Baseline**: gateway sem cache (todas as requisicoes forwarded ao agente Python)
2. **Cached**: gateway com cache semantico ativo (requisicoes repetidas servidas do cache)

---

## Decisoes Tecnicas

### Metodologia

| Aspecto | Decisao | Justificativa |
|---------|---------|---------------|
| Carga identica | Mesmo numero de requests, mesma concorrencia | Comparacao justa |
| Perguntas fixas | 5 perguntas deterministicas repetidas | Alta taxa de hit no cache, resultado reproduzivel |
| Delay controlado | Mock agent com delay configuravel (default 150ms) | Simula latencia realista do agente Python |
| Gateway mock | FastAPI mock que replica comportamento do Go | Go toolchain indisponivel no ambiente de dev |
| Normalizacao | Mesmas regras do Go `NormalizeQuestion` | Cache key consistente entre mock e producao |
| TTL do cache | 300 segundos | Balance entre frescor e reutilizacao |

### Metricas Comparadas

- **Latencia p50/p95/p99**: percentis de latencia ponta-a-ponta
- **Requests/sec**: throughput do sistema
- **Taxa de erro**: estabilidade sob carga
- **Cache hit ratio**: eficacia do cache
- **Reducao de chamadas Python**: economia de recursos do agente

### Arquitetura do Benchmark

```
┌─────────────────────────────────────────────────────────┐
│                    chat_compare.py                       │
│  (orquestrador do benchmark comparativo)                 │
│                                                          │
│  1. Inicia mock_python_agent.py (porta 9000)            │
│  2. Inicia gateway_mock (cache OFF, porta 8080)         │
│  3. Executa baseline (N requests)                       │
│  4. Para gateway, reinicia (cache ON)                   │
│  5. Executa cached (N requests, mesmas perguntas)       │
│  6. Para tudo, compara resultados                       │
│  7. Gera relatorio JSON + tabela markdown               │
└─────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌────────────────────┐      ┌────────────────────────┐
│ mock_python_agent  │◄─────│ gateway_mock_with_cache│
│ (FastAPI, porta    │      │ (FastAPI, porta 8080)  │
│  9000, delay 150ms)│      │  - cache ON/OFF        │
│                    │      │  - normalizacao igual   │
│                    │      │    ao Go                │
└────────────────────┘      └────────────────────────┘
```

---

## Implementacao

### Arquivos Criados

| Arquivo | Descricao |
|---------|-----------|
| `tools/benchmark/gateway_mock_with_cache.py` | Mock FastAPI do gateway Go com cache semantico em memoria |
| `tools/benchmark/chat_compare.py` | Script de benchmark comparativo automatico |
| `docs/2026-04-28-feature-3-4-benchmark-evidencias-ganho.md` | Esta documentacao |

### gateway_mock_with_cache.py

Mock do gateway Go que replica:

- **Contrato exato**: `POST /api/v1/chat` aceita `ChatRequest` JSON, retorna `ChatResponse`
- **Normalizacao**: `trim → lowercase → collapse spaces → remove punctuation` (mesmas regras do Go)
- **Cache key**: `chat:{project_id}:{sha256(normalized)[:16]}:{version}`
- **Cache em memoria**: dict com TTL por entrada (default 300s)
- **Latencia artificial**: ~5ms para cache hit (simula leitura Redis)
- **Metrics endpoint**: `GET /metrics` com formato Prometheus text
  - `gateway_requests_total`
  - `gateway_cache_hits_total`
  - `gateway_cache_misses_total`
  - `gateway_cache_hit_ratio`
  - `gateway_cache_size`

**Controle de cache:**
- Flag CLI: `--cache-enabled true|false`
- Env var: `CACHE_ENABLED=true|false`
- Default: `true`

### chat_compare.py

Orquestrador que:

1. Inicia `mock_python_agent.py` na porta 9000 com delay configuravel
2. Inicia `gateway_mock_with_cache.py` com `cache_enabled=false`
3. Executa benchmark baseline (reutiliza `run_benchmark` de `chat_baseline.py`)
4. Para gateway, reinicia com `cache_enabled=true`
5. Executa benchmark cached (mesmas perguntas, mesma carga)
6. Para todos os processos
7. Calcula deltas e gera relatorio

**Args CLI:**
- `--requests`: total de requests por fase (default: 50)
- `--concurrency`: concorrencia (default: 10)
- `--agent-delay-ms`: delay do agente em ms (default: 150)
- `--output`: caminho do relatorio JSON

---

## Testes Executados

### Execucao padrao

```bash
cd tools/benchmark
python chat_compare.py --output comparison_report.json
```

### Carga maior

```bash
python chat_compare.py --requests 200 --concurrency 20 --output report_200x20.json
```

### Agente mais lento (simular RAG real)

```bash
python chat_compare.py --agent-delay-ms 300 --output report_slow_agent.json
```

### Execucao manual dos componentes

```bash
# Terminal 1: mock agente
python mock_python_agent.py --port 9000 --delay-ms 150

# Terminal 2: gateway sem cache
CACHE_ENABLED=false python gateway_mock_with_cache.py --port 8080

# Terminal 3: gateway com cache
CACHE_ENABLED=true python gateway_mock_with_cache.py --port 8081

# Terminal 4: benchmark baseline
python chat_baseline.py --url http://localhost:8080 --requests 50 --concurrency 10

# Terminal 5: benchmark cached
python chat_baseline.py --url http://localhost:8081 --requests 50 --concurrency 10
```

---

## Resultados

### Template de Tabela Comparativa (Valores Esperados)

| Metrica | Sem Cache | Com Cache | Delta |
|---------|-----------|-----------|-------|
| Latencia p50 (ms) | ~160 | ~40 | -75% |
| Latencia p95 (ms) | ~180 | ~50 | -72% |
| Latencia p99 (ms) | ~200 | ~60 | -70% |
| Latencia media (ms) | ~165 | ~45 | -73% |
| Requests/sec | ~60 | ~200 | +233% |
| Taxa de erro | 0% | 0% | 0% |

### Resultados Reais

Execucao: 50 requests, 10 concorrencia, 150ms agent delay, 5 perguntas repetidas.

| Metrica | Sem Cache | Com Cache | Delta |
|---------|-----------|-----------|-------|
| Latencia p50 (ms) | 178.07 | 31.73 | **-82.2%** |
| Latencia p95 (ms) | 201.22 | 201.74 | +0.3% |
| Latencia p99 (ms) | 202.59 | 203.82 | +0.6% |
| Latencia media (ms) | 180.01 | 61.95 | **-65.6%** |
| Requests/sec | 53.90 | 155.09 | **+187.7%** |
| Taxa de erro | 0% | 0% | 0% |

### Estatisticas de Cache

| Metrica | Valor Observado | Meta |
|---------|----------------|------|
| Cache hits | 40 | — |
| Cache misses | 10 | — |
| Cache hit ratio | 80.00% | >=40% |
| Reducao chamadas Python | 80.0% | >=30% |

### Nota sobre p95/p99

Os percentis p95 e p99 **nao melhoraram** nesta carga reduzida porque a latencia de cauda e dominada pelos 10 cache misses iniciais (primeira ocorrencia de cada uma das 5 perguntas). Com 50 requests e 10 misses, os 5 requests mais lentos (p95 = 47.5° request) e os mais lentos ainda (p99 = 49.5° request) sao todos cache misses — ou seja, o p95/p99 mede essencialmente a latencia do agente Python, nao do cache.

Em producao, com mais requests por sessao e maior volume total, o ratio de misses dilui-se na cauda da distribuicao e o p95 converge para a latencia de cache hit (~5-30ms). O ganho real de p95 so aparece quando o numero de requests por pergunta >> 1, o que e o padrao esperado em uso real.

O p50 (-82.2%) e a media (-65.6%) ja demonstram o ganho efetivo: a maioria absoluta dos requests (40/50 = 80%) foi servida do cache com latencia proxima de zero. O throughput (RPS) quase triplicou (+187.7%), confirmando que o cache libera capacidade do sistema.

---

## Proximos Passos

1. **Benchmark contra gateway Go real**: quando o ambiente Go estiver disponivel, executar o mesmo benchmark contra o gateway real para validar que o mock reflete com precisao o comportamento de producao.

2. **Benchmark com distribuicao realista de perguntas**: usar log de perguntas reais (quando disponivel) para simular padrao de acesso mais proximo da producao, com mix de perguntas novas e repetidas.

3. **Benchmark de throughput maximo**: identificar o ponto de saturacao do gateway com e sem cache, variando concorrencia de 1 a 100.

4. **Integracao com CI/CD**: adicionar benchmark como gate de qualidade, falhando se:
   - p95 com cache > 100ms
   - hit ratio < 30%
   - error rate > 1%

5. **Graficos de tendencia**: armazenar resultados de benchmark ao longo do tempo para visualizar impacto de mudancas de performance.

6. **Benchmark do Redis real**: substituir cache em memoria do mock por Redis real para medir overhead de rede e validar que a latencia de ~5ms para cache hit e realista.
