# Runbook de Resposta a Incidentes

## Visao Geral

Este documento descreve procedimentos basicos de resposta a incidentes para os servicos do backend TCC.

## Classificacao de Severidade

| Severidade | Impacto | Tempo de Resposta |
|---|---|---|
| P1 - Critico | Servico indisponivel, perda de dados | Imediato |
| P2 - Alto | Degradacao significativa, funcionalidade bloqueada | 30 min |
| P3 - Medio | Impacto parcial, workaround disponivel | 2h |
| P4 - Baixo | Impacto minimo, cosmético | Proximo dia util |

## Incidentes Comuns

### 1. Servico Python (public-indexer) indisponivel

**Sintomas:**
- Health check `/api/v1/health` retorna erro ou timeout
- Alerta `ServiceDown` disparado
- Requisicoes retornam 502/503

**Diagnostico:**
```bash
# Verificar status do container
docker ps | grep public-indexer

# Verificar logs
docker logs public-indexer --tail 100

# Verificar conectividade com dependencias
curl -s http://localhost:8001/api/v1/health | jq
```

**Acoes:**
1. Verificar logs para erros de conexao (PostgreSQL, MongoDB, Redis, MinIO)
2. Se conexao com banco falhou: verificar status do PostgreSQL
3. Se OOM (Out of Memory): reiniciar container e investigar memory leak
4. Reiniciar servico: `docker compose restart public-indexer`
5. Verificar health apos reinicio

**Escalacao:** Se problema persistir apos reinicio, verificar infraestrutura (Docker, rede, disco).

### 2. Python-Agent com latencia alta

**Sintomas:**
- Alerta `PythonAgentHighLatency` disparado
- Requisicoes de chat/processamento demoram > 30s
- Timeout no Go Gateway

**Diagnostico:**
```bash
# Verificar metricas Prometheus
curl -s http://localhost:8002/metrics | grep http_request_duration

# Verificar logs de requests lentos
docker logs python-agent 2>&1 | grep "duration_ms" | sort -t: -k2 -n | tail -20
```

**Acoes:**
1. Verificar se API OpenAI esta respondendo (rate limit, downtime)
2. Verificar cache hit rate — cache miss excessivo indica problema
3. Se problema na OpenAI: habilitar modo fallback ou reduzir timeout
4. Verificar tamanho do contexto — documentos grandes podem causar lentidao

**Escalacao:** Se OpenAI estiver com downtime, comunicar usuarios e habilitar modo degradado.

### 3. Alta taxa de falhas no indexer

**Sintomas:**
- Alerta `PublicIndexerHighErrorRate` disparado
- Jobs de indexacao falhando repetidamente
- Contador `public_indexer_failures_total` crescendo rapidamente

**Diagnostico:**
```bash
# Verificar metricas de falha por estagio
curl -s http://localhost:8001/metrics | grep public_indexer_failures

# Verificar jobs falhados no MongoDB
docker exec mongodb mongosh --eval 'db.jobs.find({status: "failed"}).sort({created_at: -1}).limit(5)'
```

**Acoes:**
1. Identificar estagio da falha (artifact_download, text_extraction, embedding, vector_store)
2. Se falha em download: verificar conectividade com fontes externas (Gutenberg, OpenLibrary)
3. Se falha em embedding: verificar chave OpenAI e rate limits
4. Se falha em vector_store: verificar PostgreSQL/pgvector
5. Pausar scheduler temporariamente se falhas em cascata:
   ```bash
   curl -X POST http://localhost:8001/api/v1/admin/scheduler/pause
   ```

**Escalacao:** Se fonte externa estiver indisponivel, aguardar recuperacao e reprocessar jobs pendentes.

### 4. Lock contention no scheduler

**Sintomas:**
- Alerta `SchedulerLockContention` disparado
- Jobs de indexacao nao avancam
- Logs indicam espera por lock

**Diagnostico:**
```bash
# Verificar locks no Redis
docker exec redis redis-cli KEYS "scheduler:*"

# Verificar jobs em execucao
docker exec mongodb mongosh --eval 'db.jobs.find({status: "running"})'
```

**Acoes:**
1. Verificar se ha job travado em status "running" ha muito tempo
2. Se job travado: marcar como failed e liberar lock
   ```bash
   docker exec redis redis-cli DEL "scheduler:lock:index"
   ```
3. Reiniciar scheduler: `docker compose restart public-indexer`
4. Verificar se jobs pendentes sao processados apos reinicio

### 5. Banco de dados indisponivel

**Sintomas:**
- Erros de conexao em todos os servicos
- Health checks falhando
- Logs com "connection refused" ou "timeout"

**Diagnostico:**
```bash
# Verificar status do PostgreSQL
docker ps | grep postgres
docker logs postgres --tail 50

# Testar conexao
docker exec postgres pg_isready
```

**Acoes:**
1. Se container parado: `docker compose start postgres`
2. Se disco cheio: liberar espaco e reiniciar
3. Se corrupcao: restaurar do backup mais recente
4. Verificar conexoes ativas: `SELECT count(*) FROM pg_stat_activity;`

**Escalacao:** Se backup necessario, contatar administrador do NeonDB.

## Procedimento Geral de Incidente

1. **Detectar**: Alerta disparado ou reporte de usuario
2. **Classificar**: Definir severidade (P1-P4)
3. **Diagnosticar**: Seguir runbook especifico acima
4. **Mitigar**: Aplicar correcao ou workaround
5. **Verificar**: Confirmar que servico voltou ao normal
6. **Documentar**: Registrar incidente com causa raiz e acoes tomadas
7. **Melhorar**: Criar task para prevenir recorrencia

## Contatos

| Papel | Responsavel | Canal |
|---|---|---|
| On-call | Desenvolvedor responsavel | Slack/Discord |
| Infraestrutura | Admin do servidor | Email |
| Stakeholder | Orientador TCC | Email |

## Pos-Incidente

Apos resolver incidente P1 ou P2:
1. Preencher relatorio de incidente
2. Identificar causa raiz
3. Definir acoes preventivas
4. Atualizar runbook se necessario
5. Agendar revisao com equipe
