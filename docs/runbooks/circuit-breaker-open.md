# Runbook: Circuit Breaker Aberto

## Sintomas

- Requisicoes ao Python-Agent retornando HTTP 503
- Logs do Go-Gateway com mensagem `"circuit breaker open"`
- Metricas Prometheus: `circuit_breaker_state{service="python-agent"} == 1` (open)
- Latencia de chat aumenta drasticamente ou falha imediata

## Diagnostico

### 1. Verificar estado do circuit breaker

```bash
# Endpoint de status do breaker (se disponivel)
curl -s http://localhost:8080/api/v1/admin/circuit-breaker/status | jq

# Verificar logs do gateway
docker logs go-gateway 2>&1 | grep "circuit breaker" | tail -30
```

### 2. Verificar saude do Python-Agent

```bash
# Health check direto
curl -s http://localhost:8002/api/v1/health | jq

# Verificar se container esta rodando
docker ps | grep python-agent

# Verificar logs recentes do agent
docker logs python-agent --tail 100
```

### 3. Verificar metricas de falha

```bash
# Contagem de erros 5xx
curl -s http://localhost:8080/metrics | grep http_requests_total | grep "5[0-9][0-9]"

# Latencia do upstream
curl -s http://localhost:8080/metrics | grep upstream_duration
```

## Acoes

### 1. Verificar logs do Python-Agent

```bash
docker logs python-agent --tail 200 2>&1 | grep -iE "error|exception|traceback"
```

Buscar por:
- Erros de conexao com PostgreSQL/NeonDB
- Erros de autenticacao OpenAI (chave invalida, rate limit)
- OOM (Out of Memory) ou crashes
- Timeouts em operacoes de embedding

### 2. Verificar conectividade com banco de dados

```bash
# Testar conexao direta com PostgreSQL
docker exec postgres pg_isready

# Verificar conexoes ativas
docker exec postgres psql -U postgres -d tcc_db -c "SELECT count(*) FROM pg_stat_activity;"
```

### 3. Aguardar transicao para half-open

O circuit breaker segue o padrao:
- **Closed** → **Open**: apos N falhas consecutivas (threshold configurado)
- **Open** → **Half-Open**: apos timeout de recuperacao (ex: 30s)
- **Half-Open** → **Closed**: se probe request succeeder
- **Half-Open** → **Open**: se probe request falhar

```bash
# Monitorar transicao de estado
watch -n 5 'curl -s http://localhost:8080/api/v1/admin/circuit-breaker/status | jq'
```

### 4. Reset manual (se necessario)

Se o breaker nao transiciona automaticamente apos recuperacao do servico:

```bash
# Reset manual do circuit breaker
curl -X POST http://localhost:8080/api/v1/admin/circuit-breaker/reset \
  -H "Content-Type: application/json" \
  -d '{"service": "python-agent"}'
```

### 5. Reiniciar Python-Agent (se travado)

```bash
docker compose restart python-agent
# Aguardar 10s e verificar health
sleep 10
curl -s http://localhost:8002/api/v1/health | jq
```

## Escalacao

| Condicao | Acao | Responsavel |
|---|---|---|
| Python-Agent nao recupera apos reinicio | Verificar logs detalhados, possivel rollback de deploy | Desenvolvedor |
| OpenAI API indisponivel | Habilitar modo fallback, comunicar usuarios | Desenvolvedor |
| NeonDB indisponivel | Verificar status do NeonDB, restaurar conexao | Admin infra |
| Circuit breaker abre repetidamente | Investigar causa raiz, ajustar thresholds | Desenvolvedor + Orientador |

## Pos-Incidente

1. Registrar causa raiz no relatorio de incidente
2. Verificar se thresholds do circuit breaker estao adequados
3. Atualizar este runbook se novo padrao identificado
4. Considerar adicionar alertas proativos para pre-abertura
