// Package retry implementa politica de retry com backoff exponencial e jitter.
// Retry e aplicado apenas em operacoes idempotentes e para erros classificados
// como retryable (timeout, servico indisponivel).
package retry

import (
	"context"
	"log/slog"
	"math/rand"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Metricas Prometheus para retry.
var (
	// retryAttemptsTotal — tentativas de retry por operacao.
	retryAttemptsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "retry_attempts_total",
			Help: "Total number of retry attempts per operation",
		},
		[]string{"operation"},
	)

	// retryFailuresTotal — falhas finais apos esgotar retries por operacao.
	retryFailuresTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "retry_failures_total",
			Help: "Total number of final failures after exhausting retries per operation",
		},
		[]string{"operation"},
	)
)

// Config agrupa parametros configuraveis da politica de retry.
type Config struct {
	// MaxRetries numero maximo de tentativas adicionais apos a primeira falha.
	// Default: 3.
	MaxRetries int
	// BaseDelay duracao inicial de espera entre tentativas.
	// Default: 100ms.
	BaseDelay time.Duration
	// MaxDelay limite superior para o delay de backoff.
	// Default: 2s.
	MaxDelay time.Duration
	// RetryableErrors lista de erros que devem ser retentados.
	// Erros fora desta lista falham imediatamente sem retry.
	RetryableErrors []error
}

// Policy encapsula a logica de retry com backoff exponencial + jitter.
type Policy struct {
	maxRetries      int
	baseDelay       time.Duration
	maxDelay        time.Duration
	retryableErrors map[error]struct{}
}

// NewPolicy cria uma nova politica de retry a partir da configuracao.
// Aplica valores default para campos nao preenchidos.
func NewPolicy(cfg Config) *Policy {
	maxRetries := cfg.MaxRetries
	if maxRetries <= 0 {
		maxRetries = 3
	}

	baseDelay := cfg.BaseDelay
	if baseDelay <= 0 {
		baseDelay = 100 * time.Millisecond
	}

	maxDelay := cfg.MaxDelay
	if maxDelay <= 0 {
		maxDelay = 2 * time.Second
	}

	// Indexar erros retryable em mapa para lookup O(1).
	retryableErrors := make(map[error]struct{}, len(cfg.RetryableErrors))
	for _, err := range cfg.RetryableErrors {
		retryableErrors[err] = struct{}{}
	}

	return &Policy{
		maxRetries:      maxRetries,
		baseDelay:       baseDelay,
		maxDelay:        maxDelay,
		retryableErrors: retryableErrors,
	}
}

// Execute executa a funcao fn com retry usando backoff exponencial + jitter.
// opName identifica a operacao para fins de logging.
// A ordem de execucao: tenta fn; se falhar com erro retryable, aguarda delay
// e tenta novamente ate MaxRetries. Se contexto for cancelado, aborta.
func (p *Policy) Execute(ctx context.Context, opName string, fn func() error) error {
	var lastErr error

	for attempt := 0; attempt <= p.maxRetries; attempt++ {
		// Registrar cada tentativa (incluindo a primeira)
		retryAttemptsTotal.WithLabelValues(opName).Inc()

		// Executar a funcao
		err := fn()
		if err == nil {
			return nil
		}

		lastErr = err

		// Verificar se o erro e retryable
		if !p.isRetryable(err) {
			// Erro nao-retryable: falhar imediatamente
			slog.Warn("non-retryable error, aborting retry",
				slog.String("operation", opName),
				slog.Int("attempt", attempt+1),
				slog.String("error", err.Error()),
			)
			return err
		}

		// Se esgotou todas as tentativas, registrar falha final e retornar
		if attempt == p.maxRetries {
			retryFailuresTotal.WithLabelValues(opName).Inc()
			slog.Error("retry attempts exhausted",
				slog.String("operation", opName),
				slog.Int("total_attempts", attempt+1),
				slog.String("last_error", err.Error()),
			)
			return err
		}

		// Calcular delay com backoff exponencial: baseDelay * 2^attempt
		delay := p.baseDelay * (1 << uint(attempt))

		// Limitar ao maxDelay
		if delay > p.maxDelay {
			delay = p.maxDelay
		}

		// Adicionar jitter: varia entre 50% e 150% do delay calculado
		jitter := 0.5 + rand.Float64()
		delay = time.Duration(float64(delay) * jitter)

		// Log da tentativa de retry
		slog.Warn("retry attempt scheduled",
			slog.String("operation", opName),
			slog.Int("attempt", attempt+1),
			slog.Int("max_retries", p.maxRetries),
			slog.Duration("delay", delay),
			slog.String("error", err.Error()),
		)

		// Aguardar delay ou cancelamento do contexto
		select {
		case <-ctx.Done():
			slog.Warn("retry aborted due to context cancellation",
				slog.String("operation", opName),
				slog.Int("attempt", attempt+1),
			)
			return ctx.Err()
		case <-time.After(delay):
			// Continuar para proxima tentativa
		}
	}

	return lastErr
}

// isRetryable verifica se um erro esta na lista de erros retryable.
// Usa comparacao direta com erros sentinelas do mapa.
func (p *Policy) isRetryable(err error) bool {
	if len(p.retryableErrors) == 0 {
		return false
	}

	// Verificar correspondencia direta no mapa
	for retryable := range p.retryableErrors {
		if err == retryable {
			return true
		}
	}

	return false
}
