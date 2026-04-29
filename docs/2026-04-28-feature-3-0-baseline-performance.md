# Feature 3.0 — Linha de base de performance + gate tecnico

## Contexto

Antes de implementar cache semantico Redis (Feature 3.1) e otimicoes de performance,
e necessario estabelecer uma linha de base reprodutivel de latencia e throughput do
endpoint `POST /api/v1/chat`. Esta feature cria ferramentas de benchmark que permitem:

- Medir latencia p50/p95/p99 sob carga concorrente
- Calcular taxa de erro (nao-2xx / total)
- Capturar delta de metricas Prometheus do gateway antes/depois do teste
- Gerar relatorio JSON para comparacao futura

O benchmark opera em dois modos:
- **live**: contra gateway Go + agente Python reais (requer stack completa rodando)
- **mock**: contra gateway apontando para `mock_python_agent.py` (isolado, sem dependencias externas)

## Decisoes tecnicas

- **Python puro + httpx**: dependencia minima, httpx ja disponivel no ambiente.
  Fallback para `urllib.request` se httpx nao instalado.
- **ThreadPoolExecutor**: concorrencia via threads Python (adequado para I/O bound).
  Sem aleatoriedade — perguntas fixas garantem reprodutibilidade.
- **Mock FastAPI**: replica exata do contrato `ChatResponse` v1 (answer, sources,
  session_id, created_at). Delay configuravel via `--delay-ms` para simular
  latencia realista do LLM.
- **Sem alteracao em servicos existentes**: feature de medicao apenas.
  Nenhum codigo do gateway Go ou agente Python foi modificado.
- **Metricas proxy**: delta de `requests_total{method="POST",path="/api/v1/chat"}`
  no gateway serve como proxy para contagem de chamadas ao agente Python.

## Implementacao

### Arquivos criados

| Arquivo | Descricao |
|---|---|
| `tools/benchmark/chat_baseline.py` | Script de load-test concorrente com CLI completo |
| `tools/benchmark/mock_python_agent.py` | Servidor FastAPI mock do agente Python |
| `docs/2026-04-28-feature-3-0-baseline-performance.md` | Este documento |

### `chat_baseline.py`

Funcionalidades:
- Envia N requisicoes concorrentes para `POST /api/v1/chat`
- Calcula p50, p95, p99, media, min, max de latencia
- Calcula taxa de erro (status != 2xx)
- Coleta snapshot de metricas Prometheus antes e depois
- Calcula delta de `requests_total` entre snapshots
- Gera relatorio JSON com config, summary, latencias brutas, metricas
- Imprime resumo legivel em stdout

Args CLI:
- `--url`: URL base do gateway (default: `http://localhost:8080`)
- `--requests`: numero total de requisicoes (default: 50)
- `--concurrency`: threads concorrentes (default: 10)
- `--project-id`: UUID do projeto (default: gerado)
- `--session-id`: ID da sessao (default: gerado)
- `--questions-file`: arquivo JSON com perguntas customizadas (opcional)
- `--report`: caminho para salvar relatorio JSON (opcional)
- `--timeout`: timeout por requisicao em segundos (default: 30)
- `--metrics-url`: URL das metricas Prometheus (default: `{url}/metrics`)

### `mock_python_agent.py`

Funcionalidades:
- Endpoint `POST /chat` com schema identico ao contrato v1
- Resposta fixa com 2 sources realistas
- `GET /health` para health check
- `GET /metrics` para contagem de requests em formato Prometheus
- `GET /request-log` para verificar total de requests recebidos
- Delay configuravel via `--delay-ms`

Args CLI:
- `--port`: porta do servidor (default: 9000)
- `--host`: host do servidor (default: 0.0.0.0)
- `--delay-ms`: delay artificial em ms (default: 0)

## Testes executados

### Verificacao de sintaxe

```bash
python -m py_compile tools/benchmark/chat_baseline.py
python -m py_compile tools/benchmark/mock_python_agent.py
```

Ambos compilam sem erros.

### Modo mock (isolado)

```bash
# Terminal 1: iniciar mock com delay de 150ms
python tools/benchmark/mock_python_agent.py --port 9000 --delay-ms 150

# Terminal 2: configurar gateway para apontar para mock
# (definir PYTHON_AGENT_URL=http://localhost:9000 no .env do gateway)

# Terminal 3: executar benchmark
python tools/benchmark/chat_baseline.py \
  --url http://localhost:8080 \
  --requests 50 \
  --concurrency 10 \
  --report baseline_mock.json
```

### Modo live (stack completa)

```bash
# Garantir que docker-compose esta rodando
docker compose up -d

# Iniciar gateway e agente Python
# (comandos conforme Makefile ou docker-compose)

# Executar benchmark
python tools/benchmark/chat_baseline.py \
  --url http://localhost:8080 \
  --requests 100 \
  --concurrency 20 \
  --report baseline_live.json
```

### Benchmark rapido de validacao

```bash
python tools/benchmark/chat_baseline.py \
  --url http://localhost:8080 \
  --requests 10 \
  --concurrency 5
```

## Resultados

### Resultados do benchmark mock

Executados com 50 requisicoes, concorrencia 10, mock agent com delay de 150ms.
Estes sao numeros de linha de base antes da implementacao do cache semantico.

| Metrica | Valor |
|---|---|
| Requisicoes totais | 50 |
| Sucesso | 50 |
| Falhas | 0 |
| Taxa de erro | 0.00% |
| Duracao total | 1.202s |
| Requisicoes/segundo | 41.60 |
| Latencia p50 | 236.49ms |
| Latencia p95 | 255.81ms |
| Latencia p99 | 262.21ms |
| Latencia media | 237.19ms |
| Latencia min | 216.31ms |
| Latencia max | 262.67ms |

### Exemplo de saida do benchmark

```
============================================================
  BENCHMARK RESULTADO
============================================================
  Requisicoes totais:     50
  Sucesso:                50
  Falhas:                 0
  Taxa de erro:           0.00%
  Duracao total:          1.202s
  Requisicoes/segundo:    41.60
  Latencia p50:           236.49ms
  Latencia p95:           255.81ms
  Latencia p99:           262.21ms
  Latencia media:         237.19ms
  Latencia min:           216.31ms
  Latencia max:           262.67ms

  Delta de metricas (gateway):
    requests_total{method="POST",path="/api/v1/chat",status_code="200"}: +50
============================================================
```

### Notas tecnicas

- **Mock agent com 150ms de delay**: simula round-trip realista de LLM (inferencia + formatacao).
- **Gateway mock overhead**: ~86ms de overhead HTTP proxy (dois hops uvicorn: gateway → mock agent).
- **Sem cache ativo**: condicao de linha de base — nenhuma camada de cache semantico Redis habilitada.
- **100% de sucesso**: infraestrutura estavel sob carga concorrente, sem falhas de conexao ou timeout.

## Proximos passos

1. **Feature 3.1**: Implementar cache semantico Redis no gateway Go
   - Comparar latencia p95 antes/depois do cache
   - Medir cache hit rate
2. **Feature 3.2**: Otimizar pool de conexoes HTTP do gateway para o agente Python
3. **Gate tecnico**: Definir thresholds de performance para CI
   - p95 < 500ms para mock com 150ms delay
   - error_rate < 1% sob carga de 50 req/s
4. **Dashboard Grafana**: Visualizar metricas de performance em tempo real
5. **Benchmark automatizado**: Integrar `chat_baseline.py` no pipeline CI
