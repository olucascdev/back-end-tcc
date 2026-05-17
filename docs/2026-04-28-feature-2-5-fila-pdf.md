# Feature 2.5 — Fila Assincrona de Processamento PDF

## Contexto

O processamento de documentos PDF pelo agente Python (FastAPI+Agno) é uma operação
demorada (extração de texto, chunking, geração de embeddings). A abordagem síncrona
original bloqueava a requisição HTTP até o agente concluir, causando:

- Timeouts de gateway em documentos grandes
- Acoplamento direto entre request lifecycle e processamento
- Impossibilidade de escalar workers independentemente

A fila assíncrona desacopla aceite da requisição do processamento real, permitindo
que o gateway retorne imediatamente com um `job_id` para consulta de status.

## Decisões Técnicas

### Fila em memória (MemoryQueue)
- Implementação com canal bufferizado + mapa protegido por mutex
- `Enqueue` não-bloqueante: retorna `ErrQueueFull` se canal cheio
- `Dequeue` não-bloqueante: retorna `(nil, false)` se fila vazia
- Jobs persistem no mapa para consulta via `GetJob` mesmo após dequeue

### Worker Pool
- Pool de goroutines com polling na fila (100ms sleep entre tentativas)
- Cada worker: dequeue → update status "processing" → call Python → update status final
- Context cancel para graceful shutdown
- `sync.WaitGroup` para aguardar todos os workers pararem

### Contrato da API
- `POST /api/v1/documents/process` → 202 com `{job_id, status, document_id, project_id}`
- `GET /api/v1/documents/jobs/:job_id` → 200 com status atual ou 404 se não encontrado
- 503 quando fila cheia (`PDF_QUEUE_SIZE` atingido)

### Configuração
- `PDF_WORKERS` (default: 3) — número de goroutines no worker pool
- `PDF_QUEUE_SIZE` (default: 100) — capacidade do canal bufferizado

## Implementação

### Arquivos modificados

#### `internal/config/config.go`
- Adicionados campos `PDFWorkers int` e `PDFQueueSize int` ao struct `Config`
- Carregados de `PDF_WORKERS` e `PDF_QUEUE_SIZE` com defaults 3 e 100
- Nova função `parseIntWithDefault` para parsing com valor default explícito

#### `internal/api/v1/handlers/proxy.go`
- `ProxyProcessDocument` agora recebe `queue.Queue` como segundo parâmetro
- Em vez de chamar `client.ProcessDocument` síncrono:
  1. Cria `queue.Job` com UUID, DocumentID, ProjectID, StorageKey
  2. Chama `q.Enqueue(job)`
  3. Se `ErrQueueFull` → retorna 503
  4. Retorna 202 com job info
- Novo handler `GetJobStatus(q queue.Queue)` para `GET /documents/jobs/:job_id`
  - Retorna 404 se job não encontrado
  - Inclui `error_message` e `result` conforme disponibilidade

#### `internal/api/v1/router.go`
- `Register` agora aceita `q queue.Queue` como terceiro parâmetro
- Passa `q` para `ProxyProcessDocument` e `GetJobStatus`
- Nova rota: `docs.GET("/jobs/:job_id", handlers.GetJobStatus(q))`

#### `internal/app/app.go`
- `Setup` agora retorna `(*gin.Engine, func())` — engine + cleanup function
- Cria `queue.NewMemoryQueue(cfg.PDFQueueSize)`
- Cria `queue.NewWorkerPool(q, pythonClient, cfg.PDFWorkers)` e chama `Start()`
- `cleanup` chama `workerPool.Stop()` para graceful shutdown
- Passa `q` para `v1.Register`

#### `cmd/server/main.go`
- Recebe `cleanup` de `app.Setup(cfg)`
- Chama `cleanup()` antes de `srv.Shutdown(ctx)` para encerrar worker pool

### Arquivos existentes (não modificados)
- `internal/infrastructure/queue/queue.go` — MemoryQueue já implementada
- `internal/infrastructure/queue/worker.go` — WorkerPool já implementado
- `internal/infrastructure/queue/errors.go` — erros sentinelas já definidos

## Testes Executados

### Testes unitários atualizados
- `TestProxyProcessDocument_Success` — verifica 202 com job_id
- `TestProxyProcessDocument_Upstream502` — verifica 202 (erro tratado pelo worker)
- `TestProxyProcessDocument_Timeout504` — verifica 202 (timeout tratado pelo worker)
- `TestProxyProcessDocument_InvalidBody` — verifica 400 (validação mantida)

### Novos testes adicionados
- `TestProxyProcessDocument_QueueFull_503` — enche fila e verifica 503
- `TestGetJobStatus_Found` — consulta job existente, verifica campos
- `TestGetJobStatus_NotFound` — consulta job inexistente, verifica 404

### Execução
```bash
cd services/go-gateway && go test ./...
```

## Próximos Passos

1. **Persistência de jobs** — migrar MemoryQueue para Redis/PostgreSQL para
   sobrevivência a restarts do gateway
2. **Webhook de notificação** — callback HTTP quando job completar
3. **Métricas de fila** — expor tamanho da fila, taxa de processamento, latência
4. **Prioridade de jobs** — suporte a jobs de alta prioridade
5. **Redis-backed queue** — substituir MemoryQueue por Redis para produção
