package circuitbreaker

import (
	"errors"
	"testing"
	"time"
)

// testConfig retorna configuracao com thresholds baixos para testes rapidos.
func testConfig() Config {
	return Config{
		MaxRequests:      1,
		FailureThreshold: 3,
		Timeout:          100 * time.Millisecond,
	}
}

func TestBreakerGroup_ExecuteSuccess(t *testing.T) {
	bg := NewBreakerGroup(testConfig())

	// Execucao com sucesso deve retornar resultado sem erro
	result, err := bg.Execute("test-op", func() (interface{}, error) {
		return "ok", nil
	})

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "ok" {
		t.Errorf("expected result 'ok', got %v", result)
	}
}

func TestBreakerGroup_ExecuteFailureOpensCircuit(t *testing.T) {
	bg := NewBreakerGroup(testConfig())

	// Falhas consecutivas ate o threshold devem abrir o circuito
	for i := 0; i < 3; i++ {
		_, err := bg.Execute("test-op", func() (interface{}, error) {
			return nil, errors.New("upstream error")
		})
		if err == nil {
			t.Fatalf("expected error on failure %d", i+1)
		}
	}

	// Apos threshold, circuito deve estar aberto
	_, err := bg.Execute("test-op", func() (interface{}, error) {
		return "should not execute", nil
	})
	if err == nil {
		t.Fatal("expected error after circuit opened, got nil")
	}
	if !errors.Is(err, ErrCircuitOpen) {
		t.Errorf("expected ErrCircuitOpen, got %v", err)
	}
}

func TestBreakerGroup_OpenCircuitReturnsErrCircuitOpen(t *testing.T) {
	bg := NewBreakerGroup(testConfig())

	// Abrir circuito com falhas consecutivas
	for i := 0; i < 3; i++ {
		_, _ = bg.Execute("test-op", func() (interface{}, error) {
			return nil, errors.New("fail")
		})
	}

	// Funcao nao deve ser executada quando circuito esta aberto
	executed := false
	_, err := bg.Execute("test-op", func() (interface{}, error) {
		executed = true
		return "result", nil
	})

	if executed {
		t.Error("function should not have been executed when circuit is open")
	}
	if !errors.Is(err, ErrCircuitOpen) {
		t.Errorf("expected ErrCircuitOpen, got %v", err)
	}
}

func TestBreakerGroup_HalfOpenClosesOnSuccess(t *testing.T) {
	bg := NewBreakerGroup(Config{
		MaxRequests:      1,
		FailureThreshold: 2,
		Timeout:          50 * time.Millisecond,
	})

	// Abrir circuito com falhas
	for i := 0; i < 2; i++ {
		_, _ = bg.Execute("test-op", func() (interface{}, error) {
			return nil, errors.New("fail")
		})
	}

	// Verificar que circuito esta aberto
	_, err := bg.Execute("test-op", func() (interface{}, error) {
		return nil, nil
	})
	if !errors.Is(err, ErrCircuitOpen) {
		t.Fatalf("expected circuit to be open, got %v", err)
	}

	// Aguardar timeout para transicionar para half-open
	time.Sleep(60 * time.Millisecond)

	// Execucao com sucesso em half-open deve fechar o circuito
	result, err := bg.Execute("test-op", func() (interface{}, error) {
		return "recovered", nil
	})
	if err != nil {
		t.Fatalf("unexpected error in half-open: %v", err)
	}
	if result != "recovered" {
		t.Errorf("expected 'recovered', got %v", result)
	}

	// Circuito deve estar fechado agora — nova execucao deve funcionar
	result, err = bg.Execute("test-op", func() (interface{}, error) {
		return "normal", nil
	})
	if err != nil {
		t.Fatalf("expected circuit closed after recovery, got error: %v", err)
	}
	if result != "normal" {
		t.Errorf("expected 'normal', got %v", result)
	}
}

func TestBreakerGroup_HalfOpenReopensOnFailure(t *testing.T) {
	bg := NewBreakerGroup(Config{
		MaxRequests:      1,
		FailureThreshold: 2,
		Timeout:          50 * time.Millisecond,
	})

	// Abrir circuito com falhas
	for i := 0; i < 2; i++ {
		_, _ = bg.Execute("test-op", func() (interface{}, error) {
			return nil, errors.New("fail")
		})
	}

	// Aguardar timeout para half-open
	time.Sleep(60 * time.Millisecond)

	// Falha em half-open deve reabrir o circuito
	_, err := bg.Execute("test-op", func() (interface{}, error) {
		return nil, errors.New("fail again")
	})
	if err == nil {
		t.Fatal("expected error on half-open failure")
	}

	// Circuito deve estar aberto novamente
	_, err = bg.Execute("test-op", func() (interface{}, error) {
		return "should not execute", nil
	})
	if !errors.Is(err, ErrCircuitOpen) {
		t.Errorf("expected ErrCircuitOpen after half-open failure, got %v", err)
	}
}

func TestBreakerGroup_MultipleOperationsIndependent(t *testing.T) {
	bg := NewBreakerGroup(testConfig())

	// Abrir circuito apenas para "op-a"
	for i := 0; i < 3; i++ {
		_, _ = bg.Execute("op-a", func() (interface{}, error) {
			return nil, errors.New("fail")
		})
	}

	// "op-a" deve estar aberto
	_, err := bg.Execute("op-a", func() (interface{}, error) {
		return nil, nil
	})
	if !errors.Is(err, ErrCircuitOpen) {
		t.Errorf("expected op-a circuit open, got %v", err)
	}

	// "op-b" deve estar fechado (independente)
	result, err := bg.Execute("op-b", func() (interface{}, error) {
		return "ok", nil
	})
	if err != nil {
		t.Errorf("expected op-b to work independently, got error: %v", err)
	}
	if result != "ok" {
		t.Errorf("expected 'ok' from op-b, got %v", result)
	}
}
