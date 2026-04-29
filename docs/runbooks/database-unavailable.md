# Runbook: Banco de Dados Indisponivel

## Sintomas

- Erros de conexao em todos os servicos (Go-Gateway, Python-Agent, Public-Indexer)
- Health checks falhando com status de dependencias
- Logs com "connection refused", "connection timeout", "could not connect to server"
- Requisicoes de chat e processamento retornando HTTP 500
- Servicos em estado de degradacao ou indisponibilidade total

## Diagnostico

### 1. Verificar status do NeonDB/PostgreSQL

```bash
# Se PostgreSQL local (docker)
docker ps | grep postgres
docker logs postgres --tail 50

# Testar conexao
docker exec postgres pg_isready -U postgres -d tcc_db

# Se NeonDB (serverless)
# Verificar status no dashboard do Neon: https://console.neon.tech
# Verificar se projeto esta ativo e sem suspensao automatica
```

### 2. Verificar pool de conexoes

```bash
# Conexoes ativas no PostgreSQL
docker exec postgres psql -U postgres -d tcc_db -c \
  "SELECT count(*) as total, state FROM pg_stat_activity GROUP BY state;"

# Verificar limite maximo de conexoes
docker exec postgres psql -U postgres -d tcc_db -c \
  "SHOW max_connections;"

# Metricas do pool (se expostas via Prometheus)
curl -s http://localhost:8080/metrics | grep db_pool
curl -s http://localhost:8002/metrics | grep db_pool
```

### 3. Verificar rede e conectividade

```bash
# Testar conexao de dentro dos containers
docker exec go-gateway nc -zv postgres 5432
docker exec python-agent nc -zv postgres 5432

# Verificar DNS interno do Docker
docker exec go-gateway getent hosts postgres

# Verificar se porta esta acessivel
docker exec postgres ss -tlnp | grep 5432
```

## Acoes

### 1. Verificar e restaurar rede

```bash
# Verificar rede Docker
docker network ls
docker network inspect tcc_backend

# Reconectar servicos a rede se necessario
docker network connect tcc_backend postgres
```

### 2. Verificar limites de conexao

Se o numero de conexoes atingiu o limite:

```bash
# Identificar conexoes idle ha muito tempo
docker exec postgres psql -U postgres -d tcc_db -c \
  "SELECT pid, state, query, backend_start, state_change
   FROM pg_stat_activity
   WHERE state = 'idle'
   AND state_change < NOW() - INTERVAL '5 minutes'
   ORDER BY state_change;"

# Terminar conexoes idle (cuidado: pode afetar servicos)
docker exec postgres psql -U postgres -d tcc_db -c \
  "SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE state = 'idle'
   AND state_change < NOW() - INTERVAL '5 minutes'
   AND pid != pg_backend_pid();"
```

### 3. Reiniciar pools de conexao

```bash
# Reiniciar servicos para forcar recreacao dos pools
docker compose restart go-gateway python-agent public-indexer

# Aguardar inicializacao
sleep 10

# Verificar health de cada servico
curl -s http://localhost:8080/health | jq
curl -s http://localhost:8002/api/v1/health | jq
curl -s http://localhost:8001/api/v1/health | jq
```

### 4. Habilitar modo fallback

Se o banco permanece indisponivel, habilitar modo degradado:

```bash
# Go-Gateway: habilitar modo offline/cache
# (depende da implementacao - verificar feature flags)

# Python-Agent: usar cache local se disponivel
# Verificar se REDIS_URL esta configurado e Redis disponivel
docker exec redis redis-cli ping
```

### 5. Reiniciar PostgreSQL (se local)

```bash
# Reinicio graceful
docker compose restart postgres

# Se nao responder, forcar reinicio
docker compose stop postgres
docker compose start postgres

# Aguardar inicializacao completa
sleep 15
docker exec postgres pg_isready
```

### 6. Restaurar backup (se corrupcao)

```bash
# Verificar backups disponiveis
ls -la /backups/  # ou caminho configurado

# Restaurar ultimo backup
docker exec -i postgres psql -U postgres -d tcc_db < /backups/latest.sql

# Ou via pg_restore
docker exec -i postgres pg_restore -U postgres -d tcc_db < /backups/latest.dump
```

## Escalacao

| Condicao | Acao | Responsavel |
|---|---|---|
| NeonDB suspenso/inativo | Acessar console Neon, reativar projeto | Admin infra |
| Disco cheio no PostgreSQL | Liberar espaco, expandir volume | Admin infra |
| Corrupcao de dados | Restaurar backup, verificar integridade | Admin infra + Desenvolvedor |
| Indisponibilidade prolongada (> 30 min) | Comunicar stakeholders, ativar plano contingencia | Orientador + Desenvolvedor |
| Perda de dados confirmada | Avaliar impacto, documentar perdas | Orientador |

## Pos-Incidente

1. Registrar tempo total de indisponibilidade e servicos afetados
2. Verificar se connection pools estao configurados corretamente
3. Avaliar se limites de conexao sao adequados para carga
4. Considerar implementar health check mais agressivo para DB
5. Adicionar alerta de conexoes proximas do limite
6. Atualizar este runbook se novo padrao identificado
