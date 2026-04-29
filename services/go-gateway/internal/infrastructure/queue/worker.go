package queue

import (
	"context"
	"log/slog"
	"sync"
	"time"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
	"github.com/olucasdev/tcc/go-gateway/internal/application/webhook"
)

// WorkerPool gerencia um pool de goroutines que processam jobs da fila
// de forma concorrente, chamando o agente Python para cada job.
type WorkerPool struct {
	queue          Queue
	client         *python.Client
	numWorkers     int
	wg             sync.WaitGroup
	ctx            context.Context
	cancel         context.CancelFunc
	webhookService *webhook.Service
}

// NewWorkerPool cria um novo pool de workers com a fila e cliente Python fornecidos.
func NewWorkerPool(queue Queue, client *python.Client, numWorkers int) *WorkerPool {
	return &WorkerPool{
		queue:      queue,
		client:     client,
		numWorkers: numWorkers,
	}
}

// NewWorkerPoolWithWebhook cria um pool de workers com servico de webhook
// para notificacao de status de documento ao BFF.
func NewWorkerPoolWithWebhook(queue Queue, client *python.Client, numWorkers int, webhookService *webhook.Service) *WorkerPool {
	return &WorkerPool{
		queue:          queue,
		client:         client,
		numWorkers:     numWorkers,
		webhookService: webhookService,
	}
}

// Start inicia o pool de workers, criando uma goroutine para cada worker.
// Cada worker faz polling na fila e processa jobs disponiveis.
func (wp *WorkerPool) Start() {
	wp.ctx, wp.cancel = context.WithCancel(context.Background())

	for i := 0; i < wp.numWorkers; i++ {
		wp.wg.Add(1)
		go wp.worker(i)
	}

	slog.Info("worker pool started", slog.Int("workers", wp.numWorkers))
}

// Stop sinaliza o cancelamento do contexto e aguarda todos os workers terminarem.
func (wp *WorkerPool) Stop() {
	wp.cancel()
	wp.wg.Wait()
	slog.Info("worker pool stopped")
}

// worker executa o loop principal de um worker individual.
// Faz polling na fila, processa jobs e atualiza status conforme resultado.
func (wp *WorkerPool) worker(id int) {
	defer wp.wg.Done()

	slog.Info("worker started", slog.Int("worker_id", id))

	for {
		// Verificar se o contexto foi cancelado
		select {
		case <-wp.ctx.Done():
			slog.Info("worker stopping", slog.Int("worker_id", id))
			return
		default:
		}

		// Tentar obter proximo job da fila (nao bloqueante)
		job, ok := wp.queue.Dequeue()
		if !ok {
			// Fila vazia — aguardar antes de proximo polling
			time.Sleep(100 * time.Millisecond)
			continue
		}

		wp.processJob(id, job)
	}
}

// processJob executa o processamento de um unico job.
// Atualiza status para processing, chama o agente Python, e atualiza status final.
func (wp *WorkerPool) processJob(workerID int, job *Job) {
	start := time.Now()

	slog.Info("worker processing job",
		slog.Int("worker_id", workerID),
		slog.String("job_id", job.ID),
		slog.String("document_id", job.DocumentID.String()),
	)

	// Atualizar status para processing
	if err := wp.queue.UpdateStatus(job.ID, StatusProcessing, nil, nil); err != nil {
		slog.Error("failed to update job status to processing",
			slog.String("job_id", job.ID),
			slog.String("error", err.Error()),
		)
		return
	}

	// Construir request para o agente Python
	req := &v1.ProcessDocumentRequest{
		ProjectID:  job.ProjectID,
		DocumentID: job.DocumentID,
		StorageKey: job.StorageKey,
	}

	// Chamar agente Python
	resp, err := wp.client.ProcessDocument(wp.ctx, req)
	if err != nil {
		errMsg := err.Error()
		slog.Error("job processing failed",
			slog.String("job_id", job.ID),
			slog.String("document_id", job.DocumentID.String()),
			slog.String("error", errMsg),
		)

		// Atualizar status para error
		if updateErr := wp.queue.UpdateStatus(job.ID, StatusError, &errMsg, nil); updateErr != nil {
			slog.Error("failed to update job status to error",
				slog.String("job_id", job.ID),
				slog.String("error", updateErr.Error()),
			)
		}

		// Observar duracao do processamento com falha
		pdfQueueProcessingDuration.WithLabelValues("error").Observe(time.Since(start).Seconds())

		// Enviar webhook de notificacao (best-effort, nao falha o job)
		wp.sendWebhookWithRetry(job, StatusError, &errMsg)

		return
	}

	slog.Info("job processing completed",
		slog.String("job_id", job.ID),
		slog.String("document_id", job.DocumentID.String()),
		slog.String("status", resp.Status),
	)

	// Atualizar status para ready com resultado
	if updateErr := wp.queue.UpdateStatus(job.ID, StatusReady, nil, resp); updateErr != nil {
		slog.Error("failed to update job status to ready",
			slog.String("job_id", job.ID),
			slog.String("error", updateErr.Error()),
		)
	}

	// Observar duracao do processamento com sucesso
	pdfQueueProcessingDuration.WithLabelValues("ready").Observe(time.Since(start).Seconds())

	// Enviar webhook de notificacao (best-effort, nao falha o job)
	wp.sendWebhookWithRetry(job, StatusReady, nil)
}

// sendWebhookWithRetry envia webhook com retry exponencial simples.
// Maximo 3 tentativas com backoff de 1s, 2s, 4s.
// Falha no webhook nao propaga erro — e best-effort.
func (wp *WorkerPool) sendWebhookWithRetry(job *Job, status string, errMsg *string) {
	if wp.webhookService == nil || !wp.webhookService.IsEnabled() {
		return
	}

	payload := &v1.DocumentStatusWebhook{
		DocumentID:   job.DocumentID,
		ProjectID:    job.ProjectID,
		Status:       status,
		Timestamp:    time.Now(),
		ErrorMessage: errMsg,
	}

	// Backoff: 1s, 2s, 4s
	backoffs := []time.Duration{1 * time.Second, 2 * time.Second, 4 * time.Second}

	for attempt, delay := range backoffs {
		err := wp.webhookService.SendWebhook(payload)
		if err == nil {
			return
		}

		slog.Warn("webhook delivery failed, will retry",
			slog.String("job_id", job.ID),
			slog.Int("attempt", attempt+1),
			slog.String("error", err.Error()),
		)

		// Aguardar backoff antes de proxima tentativa (respeita cancelamento do contexto)
		select {
		case <-wp.ctx.Done():
			return
		case <-time.After(delay):
		}
	}

	slog.Error("webhook delivery failed after all retries",
		slog.String("job_id", job.ID),
		slog.String("document_id", job.DocumentID.String()),
	)
}
