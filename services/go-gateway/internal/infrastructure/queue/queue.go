// Package queue implementa fila concorrente em memoria para processamento
// assincrono de documentos PDF.
package queue

import (
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
)

// Metricas Prometheus para fila de processamento PDF.
var (
	// pdfQueueDepth — numero de jobs aguardando no canal.
	pdfQueueDepth = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "pdf_queue_depth",
			Help: "Number of jobs waiting in the PDF processing queue",
		},
	)

	// pdfQueueJobsTotal — contador de jobs por status.
	pdfQueueJobsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "pdf_queue_jobs_total",
			Help: "Total number of PDF queue jobs by status",
		},
		[]string{"status"},
	)

	// pdfQueueProcessingDuration — tempo de processamento por job.
	pdfQueueProcessingDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "pdf_queue_processing_duration_seconds",
			Help:    "Time spent processing a PDF queue job",
			Buckets: []float64{0.5, 1, 2.5, 5, 10, 25, 50, 100, 250, 500},
		},
		[]string{"status"},
	)
)

// Status validos para um job na fila.
const (
	StatusPending    = "pending"
	StatusProcessing = "processing"
	StatusReady      = "ready"
	StatusError      = "error"
)

// Job representa uma unidade de trabalho de processamento de documento.
type Job struct {
	ID         string
	DocumentID uuid.UUID
	ProjectID  uuid.UUID
	StorageKey string
	Status     string
	CreatedAt  time.Time
	UpdatedAt  time.Time
	ErrorMessage *string
	Result     *v1.ProcessDocumentResponse
}

// Queue define a interface para operacoes de fila de jobs.
type Queue interface {
	// Enqueue adiciona um job a fila. Retorna erro se a fila estiver cheia.
	Enqueue(job *Job) error
	// Dequeue remove e retorna o proximo job da fila.
	// Retorna (job, true) se houver job disponivel, ou (nil, false) se a fila estiver vazia.
	Dequeue() (*Job, bool)
	// UpdateStatus atualiza o status de um job existente.
	UpdateStatus(jobID string, status string, errorMsg *string, result *v1.ProcessDocumentResponse) error
	// GetJob recupera um job pelo ID.
	GetJob(jobID string) (*Job, bool)
}

// MemoryQueue implementa Queue usando canal bufferizado e mapa protegido por mutex.
type MemoryQueue struct {
	ch   chan *Job
	jobs map[string]*Job
	mu   sync.RWMutex
}

// NewMemoryQueue cria uma nova fila em memoria com tamanho de buffer configuravel.
func NewMemoryQueue(bufferSize int) *MemoryQueue {
	return &MemoryQueue{
		ch:   make(chan *Job, bufferSize),
		jobs: make(map[string]*Job),
	}
}

// Enqueue adiciona um job a fila e ao mapa de rastreamento.
// Insere no mapa primeiro para evitar race condition: se worker fizer Dequeue + UpdateStatus
// antes da insercao no mapa, UpdateStatus retornaria ErrJobNotFound.
func (q *MemoryQueue) Enqueue(job *Job) error {
	// Inserir no mapa primeiro (protegido por mutex)
	q.mu.Lock()
	q.jobs[job.ID] = job
	q.mu.Unlock()

	// Tentar enviar ao canal bufferizado (nao bloqueante se houver espaco)
	select {
	case q.ch <- job:
		// Registrar metricas de enfileiramento
		pdfQueueJobsTotal.WithLabelValues("enqueued").Inc()
		pdfQueueDepth.Set(float64(len(q.ch)))
		return nil
	default:
		// Canal cheio — reverter insercao no mapa para evitar vazamento de memoria
		q.mu.Lock()
		delete(q.jobs, job.ID)
		q.mu.Unlock()
		return ErrQueueFull
	}
}

// Dequeue remove e retorna o proximo job da fila.
// Retorna (nil, false) imediatamente se a fila estiver vazia (nao bloqueante).
func (q *MemoryQueue) Dequeue() (*Job, bool) {
	select {
	case job := <-q.ch:
		return job, true
	default:
		return nil, false
	}
}

// UpdateStatus atualiza o status de um job e seus campos associados.
// Retorna erro se o job nao for encontrado.
func (q *MemoryQueue) UpdateStatus(jobID string, status string, errorMsg *string, result *v1.ProcessDocumentResponse) error {
	q.mu.Lock()
	defer q.mu.Unlock()

	job, ok := q.jobs[jobID]
	if !ok {
		return ErrJobNotFound
	}

	job.Status = status
	job.UpdatedAt = time.Now()
	job.ErrorMessage = errorMsg
	job.Result = result

	// Registrar metrica de transicao de status
	pdfQueueJobsTotal.WithLabelValues(status).Inc()

	return nil
}

// GetJob recupera um job pelo ID.
// Retorna (job, true) se encontrado, ou (nil, false) caso contrario.
func (q *MemoryQueue) GetJob(jobID string) (*Job, bool) {
	q.mu.RLock()
	defer q.mu.RUnlock()

	job, ok := q.jobs[jobID]
	if !ok {
		return nil, false
	}

	// Retornar copia para evitar race conditions
	jobCopy := *job
	return &jobCopy, true
}
