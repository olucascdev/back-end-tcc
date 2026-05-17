# Runbook: Fila PDF Congestionada

## Sintomas

- Jobs de processamento de PDF pendentes por tempo excessivo (> 5 min)
- Profundidade da fila crescendo continuamente
- Logs do Go-Gateway com `"pdf_queue_depth"` acima do threshold
- Usuarios relatam que documentos nao sao processados
- Workers da fila com status ocupado indefinidamente

## Diagnostico

### 1. Verificar profundidade da fila

```bash
# Via Redis (se fila usa Redis como backend)
docker exec redis redis-cli LLEN "pdf_queue:jobs"

# Via metricas Prometheus
curl -s http://localhost:8080/metrics | grep pdf_queue_depth

# Verificar jobs pendentes
docker exec redis redis-cli LRANGE "pdf_queue:jobs" 0 -1 | head -20
```

### 2. Verificar status do worker pool

```bash
# Metricas de workers
curl -s http://localhost:8080/metrics | grep pdf_worker

# Verificar processos de worker ativos
docker ps | grep worker

# Logs dos workers
docker logs go-gateway 2>&1 | grep "pdf.*worker" | tail -30
```

### 3. Verificar tempos de processamento

```bash
# Jobs em processamento ha muito tempo
docker exec redis redis-cli HGETALL "pdf_queue:processing"

# Metricas de duracao
curl -s http://localhost:8080/metrics | grep pdf_processing_duration
```

### 4. Verificar conectividade com MinIO/S3

```bash
# Testar conexao com MinIO
curl -s http://localhost:9000/minio/health/live

# Verificar bucket de documentos
docker exec mc mc ls local/documents 2>/dev/null || echo "mc not available"

# Logs do MinIO
docker logs minio --tail 50
```

## Acoes

### 1. Escalar workers temporariamente

```bash
# Aumentar numero de workers via variavel de ambiente
# No docker-compose.yml, ajustar PDF_WORKER_COUNT ou equivalente
# Ou reiniciar com mais replicas:
docker compose up -d --scale pdf-worker=4
```

### 2. Limpar jobs stale (travados)

```bash
# Identificar jobs travados (em processamento ha > 10 min)
docker exec redis redis-cli HGETALL "pdf_queue:processing"

# Remover jobs stale manualmente
# Substituir JOB_ID pelo ID real do job travado
docker exec redis redis-cli HDEL "pdf_queue:processing" "JOB_ID"
docker exec redis redis-cli LREM "pdf_queue:jobs" 0 "JOB_ID"

# Ou limpar toda a fila de processamento (cuidado: perde jobs em andamento)
docker exec redis redis-cli DEL "pdf_queue:processing"
```

### 3. Verificar e restaurar conectividade com MinIO

```bash
# Se MinIO estiver indisponivel:
docker compose restart minio

# Aguardar inicializacao
sleep 5

# Verificar health
curl -s http://localhost:9000/minio/health/live
```

### 4. Pausar ingestao de novos jobs (se necessario)

Se a fila esta crescendo mais rapido que o processamento:

```bash
# Pausar endpoint de upload temporariamente
# (implementar via feature flag ou nginx rule)

# Ou rate-limitar uploads:
# Adicionar regra de rate limit no gateway
```

### 5. Reprocessar jobs falhados

```bash
# Listar jobs com status failed
docker exec redis redis-cli LRANGE "pdf_queue:failed" 0 -1

# Mover jobs falhados de volta para a fila principal
# (implementar script de retry ou comando manual)
```

## Escalacao

| Condicao | Acao | Responsavel |
|---|---|---|
| MinIO indisponivel | Reiniciar container, verificar disco | Admin infra |
| Workers travados repetidamente | Investigar memory leak ou deadlock | Desenvolvedor |
| Fila cresce sem limite | Aumentar workers permanentemente, revisar arquitetura | Desenvolvedor + Orientador |
| Jobs falham por documento corrompido | Isolar documento, notificar usuario | Desenvolvedor |

## Pos-Incidente

1. Registrar numero de jobs afetados e tempo de indisponibilidade
2. Verificar se capacidade do worker pool esta dimensionada corretamente
3. Considerar implementar dead-letter queue para jobs falhados
4. Adicionar alerta de profundidade de fila com threshold proativo
5. Atualizar este runbook se novo padrao identificado
