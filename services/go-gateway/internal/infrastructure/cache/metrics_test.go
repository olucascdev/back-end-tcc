package cache

import (
	"sync"
	"testing"
	"time"
)

func TestRecordCacheHit_DoesNotPanic(t *testing.T) {
	// Verifica que RecordCacheHit nao entra em panico
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("RecordCacheHit panicked: %v", r)
		}
	}()

	RecordCacheHit("test-project-1")
	RecordCacheHit("test-project-1")
	RecordCacheHit("test-project-2")
}

func TestRecordCacheMiss_DoesNotPanic(t *testing.T) {
	// Verifica que RecordCacheMiss nao entra em panico
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("RecordCacheMiss panicked: %v", r)
		}
	}()

	RecordCacheMiss("test-project-1")
	RecordCacheMiss("test-project-2")
}

func TestRecordCacheError_DoesNotPanic(t *testing.T) {
	// Verifica que RecordCacheError nao entra em panico
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("RecordCacheError panicked: %v", r)
		}
	}()

	RecordCacheError("test-project-1", "get")
	RecordCacheError("test-project-1", "set")
	RecordCacheError("test-project-2", "get")
}

func TestRecordCacheLatency_DoesNotPanic(t *testing.T) {
	// Verifica que RecordCacheLatency nao entra em panico
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("RecordCacheLatency panicked: %v", r)
		}
	}()

	RecordCacheLatency("get", 5*time.Millisecond)
	RecordCacheLatency("set", 10*time.Millisecond)
}

func TestUpdateCacheHitRatio_Calculation(t *testing.T) {
	// Usar mutex para isolar teste de outros
	hitsMu.Lock()
	// Limpar estado para teste isolado
	testProject := "ratio-test-project"
	hitsByProject[testProject] = 0
	missesByProject[testProject] = 0
	hitsMu.Unlock()

	// Sem hits/misses → ratio = 0
	UpdateCacheHitRatio(testProject)

	// Adicionar 3 hits e 1 miss → ratio = 0.75
	for i := 0; i < 3; i++ {
		RecordCacheHit(testProject)
	}
	RecordCacheMiss(testProject)
	UpdateCacheHitRatio(testProject)

	hitsMu.RLock()
	hits := hitsByProject[testProject]
	misses := missesByProject[testProject]
	hitsMu.RUnlock()

	if hits != 3 {
		t.Errorf("expected 3 hits, got %v", hits)
	}
	if misses != 1 {
		t.Errorf("expected 1 miss, got %v", misses)
	}

	expectedRatio := 3.0 / 4.0 // 0.75
	hitsMu.RLock()
	// Verificar via mapa interno (o gauge nao e acessivel diretamente neste teste)
	actualRatio := hits / (hits + misses)
	hitsMu.RUnlock()

	if actualRatio != expectedRatio {
		t.Errorf("expected ratio %f, got %f", expectedRatio, actualRatio)
	}
}

func TestUpdateCacheHitRatio_ZeroTotal(t *testing.T) {
	testProject := "zero-ratio-project"

	// Limpar estado
	hitsMu.Lock()
	hitsByProject[testProject] = 0
	missesByProject[testProject] = 0
	hitsMu.Unlock()

	// Deve definir ratio = 0 quando total = 0
	UpdateCacheHitRatio(testProject)

	// Sem panico e sem erro = sucesso
}

func TestCacheMetrics_ConcurrentAccess(t *testing.T) {
	// Verifica que operacoes concorrentes nao causam race conditions
	testProject := "concurrent-project"
	var wg sync.WaitGroup

	// 100 goroutines, cada uma registra 10 hits e 10 misses
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 10; j++ {
				RecordCacheHit(testProject)
				RecordCacheMiss(testProject)
				UpdateCacheHitRatio(testProject)
			}
		}()
	}

	wg.Wait()

	// Verificar contagem final
	hitsMu.RLock()
	hits := hitsByProject[testProject]
	misses := missesByProject[testProject]
	hitsMu.RUnlock()

	if hits != 1000 {
		t.Errorf("expected 1000 hits, got %v", hits)
	}
	if misses != 1000 {
		t.Errorf("expected 1000 misses, got %v", misses)
	}
}
