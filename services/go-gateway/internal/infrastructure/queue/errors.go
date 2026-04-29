package queue

import "errors"

// Erros sentinelas para operacoes de fila.
var (
	ErrQueueFull    = errors.New("queue is full")
	ErrJobNotFound  = errors.New("job not found")
)
