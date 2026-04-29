// Package circuitbreaker implementa circuit breaker por operacao usando
// gobreaker. Um breaker independente e mantido para cada operacao
// (chat, summarize, compare, process-document).
package circuitbreaker

import (
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/sony/gobreaker"
)

// Metricas Prometheus para circuit breaker.
var (
	// circuitBreakerState — estado atual do breaker por operacao.
	// Valores: 0=closed, 1=open, 2=half-open.
	circuitBreakerState = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "circuit_breaker_state",
			Help: "Current state of the circuit breaker per operation (0=closed, 1=open, 2=half-open)",
		},
		[]string{"operation"},
	)

	// circuitBreakerTransitions — contador de transicoes de estado por operacao.
	circuitBreakerTransitions = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "circuit_breaker_transitions_total",
			Help: "Total number of circuit breaker state transitions per operation",
		},
		[]string{"operation", "from", "to"},
	)
)

// stateToMetric converte gobreaker.State para valor numerico da metrica.
func stateToMetric(s gobreaker.State) float64 {
	switch s {
	case gobreaker.StateOpen:
		return 1
	case gobreaker.StateHalfOpen:
		return 2
	default: // StateClosed
		return 0
	}
}

// stateName retorna nome legivel do estado para labels.
func stateName(s gobreaker.State) string {
	switch s {
	case gobreaker.StateOpen:
		return "open"
	case gobreaker.StateHalfOpen:
		return "half-open"
	default:
		return "closed"
	}
}

// ErrCircuitOpen retornado quando o circuito esta aberto e a chamada
// e rejeitada imediatamente sem tentar o upstream.
var ErrCircuitOpen = errors.New("circuit breaker open: upstream service temporarily unavailable")

// Config agrupa parametros configuraveis do circuit breaker.
type Config struct {
	// MaxRequests permite quantas requisicoes sao aceitas no estado half-open.
	MaxRequests uint32
	// FailureThreshold numero de falhas consecutivas para abrir o circuito.
	FailureThreshold uint32
	// Timeout duracao do estado open antes de transicionar para half-open.
	Timeout time.Duration
}

// DefaultConfig retorna configuracao padrao segura para producao.
func DefaultConfig() Config {
	return Config{
		MaxRequests:      3,
		FailureThreshold: 5,
		Timeout:          30 * time.Second,
	}
}

// BreakerGroup mantem um circuit breaker independente por nome de operacao.
type BreakerGroup struct {
	breakers map[string]*gobreaker.CircuitBreaker
	cfg      Config
	mu       sync.RWMutex
}

// NewBreakerGroup cria um grupo de breakers com a configuracao fornecida.
func NewBreakerGroup(cfg Config) *BreakerGroup {
	return &BreakerGroup{
		breakers: make(map[string]*gobreaker.CircuitBreaker),
		cfg:      cfg,
	}
}

// getOrCreate retorna o breaker existente ou cria um novo para a operacao.
// Thread-safe: usa RWMutex para leitura concorrente e write lock para criacao.
func (bg *BreakerGroup) getOrCreate(opName string) *gobreaker.CircuitBreaker {
	// Fast path: leitura concorrente
	bg.mu.RLock()
	cb, ok := bg.breakers[opName]
	bg.mu.RUnlock()
	if ok {
		return cb
	}

	// Slow path: criar com write lock
	bg.mu.Lock()
	defer bg.mu.Unlock()

	// Verificar novamente apos adquirir write lock (double-check)
	if cb, ok = bg.breakers[opName]; ok {
		return cb
	}

	settings := gobreaker.Settings{
		Name:          opName,
		MaxRequests:   bg.cfg.MaxRequests,
		Interval:      0, // sem reset periodico; usa apenas Timeout
		Timeout:       bg.cfg.Timeout,
		ReadyToTrip: func(counts gobreaker.Counts) bool {
			return counts.ConsecutiveFailures >= bg.cfg.FailureThreshold
		},
		OnStateChange: func(name string, from gobreaker.State, to gobreaker.State) {
			// Registrar transicao de estado nas metricas Prometheus
			circuitBreakerTransitions.WithLabelValues(name, stateName(from), stateName(to)).Inc()
			// Atualizar gauge de estado atual
			circuitBreakerState.WithLabelValues(name).Set(stateToMetric(to))
		},
	}

	cb = gobreaker.NewCircuitBreaker(settings)
	bg.breakers[opName] = cb
	return cb
}

// Execute executa a funcao fn dentro do circuit breaker da operacao.
// Se o circuito estiver aberto, retorna ErrCircuitOpen imediatamente.
// Se o circuito estiver half-open, permite requests de teste.
func (bg *BreakerGroup) Execute(opName string, fn func() (interface{}, error)) (interface{}, error) {
	cb := bg.getOrCreate(opName)

	result, err := cb.Execute(func() (interface{}, error) {
		return fn()
	})

	// Mapear erro do gobreaker para erro sentinela do projeto
	if err != nil {
		if errors.Is(err, gobreaker.ErrOpenState) {
			return nil, ErrCircuitOpen
		}
		return nil, fmt.Errorf("circuit breaker %s: %w", opName, err)
	}

	return result, nil
}

// State retorna o estado atual do breaker de uma operacao.
// Util para metricas e health checks.
func (bg *BreakerGroup) State(opName string) gobreaker.State {
	cb := bg.getOrCreate(opName)
	return cb.State()
}
