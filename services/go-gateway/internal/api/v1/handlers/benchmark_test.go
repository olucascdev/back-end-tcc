package handlers

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/olucasdev/tcc/go-gateway/internal/client/python"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/circuitbreaker"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/queue"
	"github.com/olucasdev/tcc/go-gateway/internal/middleware"
)

// setupBenchmarkTestRouter cria router com handlers de benchmark e middleware admin.
// pythonURL aponta para um mock server; adminKey define a chave de administracao.
func setupBenchmarkTestRouter(pythonURL string, adminKey string) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(middleware.RequestID())

	breakers := circuitbreaker.NewBreakerGroup(circuitbreaker.DefaultConfig())
	client := python.NewClient(pythonURL, map[string]time.Duration{
		"chat": 5 * time.Second,
	}, breakers)

	v1Group := r.Group("/api/v1")
	admin := v1Group.Group("/admin", middleware.AdminAuth(adminKey))
	{
		benchmarkRunner := NewBenchmarkRunner(client)
		admin.POST("/benchmark/load", benchmarkRunner.LoadBenchmark())
		admin.GET("/benchmark/load/:run_id", benchmarkRunner.GetBenchmarkStatus())
		admin.GET("/metrics/internal", GetInternalMetrics(client, queue.NewMemoryQueue(100)))
	}
	return r
}

func TestBenchmarkLoad_Returns202AndRunID(t *testing.T) {
	// Mock Python server que responde com sucesso
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"answer":"ok","sources":[],"session_id":"","created_at":"2024-01-01T00:00:00Z"}`))
	}))
	defer server.Close()

	r := setupBenchmarkTestRouter(server.URL, "test-admin-key")

	body := strings.NewReader(`{
		"target_endpoint": "chat",
		"concurrency": 2,
		"duration_seconds": 1,
		"payload": {"project_id":"00000000-0000-0000-0000-000000000001","session_id":"test","message":"ola"}
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/benchmark/load", body)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Admin-API-Key", "test-admin-key")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusAccepted {
		t.Errorf("expected status 202, got %d", w.Code)
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}

	runID, ok := resp["run_id"]
	if !ok {
		t.Fatal("expected run_id in response")
	}
	if runID == "" {
		t.Error("expected non-empty run_id")
	}

	status, ok := resp["status"]
	if !ok {
		t.Fatal("expected status in response")
	}
	if status != "accepted" {
		t.Errorf("expected status 'accepted', got %v", status)
	}
}

func TestBenchmarkLoadStatus_NonExistentRunID_Returns404(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	r := setupBenchmarkTestRouter(server.URL, "test-admin-key")

	req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/benchmark/load/non-existent-id", nil)
	req.Header.Set("X-Admin-API-Key", "test-admin-key")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected status 404, got %d", w.Code)
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}

	errMsg, ok := resp["error"]
	if !ok {
		t.Fatal("expected error in response")
	}
	if errMsg != "benchmark run not found" {
		t.Errorf("expected error 'benchmark run not found', got %v", errMsg)
	}
}

func TestBenchmarkLoad_Unauthorized_Returns403(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	r := setupBenchmarkTestRouter(server.URL, "test-admin-key")

	body := strings.NewReader(`{
		"target_endpoint": "chat",
		"concurrency": 1,
		"duration_seconds": 1,
		"payload": {"project_id":"00000000-0000-0000-0000-000000000001","session_id":"test","message":"ola"}
	}`)

	// Sem chave de administracao
	req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/benchmark/load", body)
	req.Header.Set("Content-Type", "application/json")
	// Nao define X-Admin-API-Key
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected status 403, got %d", w.Code)
	}
}

func TestBenchmarkLoadStatus_Unauthorized_Returns403(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	r := setupBenchmarkTestRouter(server.URL, "test-admin-key")

	// Chave invalida
	req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/benchmark/load/some-id", nil)
	req.Header.Set("X-Admin-API-Key", "wrong-key")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected status 403, got %d", w.Code)
	}
}

func TestBenchmarkLoad_InvalidTarget_Returns400(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	r := setupBenchmarkTestRouter(server.URL, "test-admin-key")

	body := strings.NewReader(`{
		"target_endpoint": "unknown-endpoint",
		"concurrency": 1,
		"duration_seconds": 1,
		"payload": {"message":"ola"}
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/benchmark/load", body)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Admin-API-Key", "test-admin-key")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected status 400, got %d", w.Code)
	}
}

func TestBenchmarkLoad_InvalidBody_Returns400(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	r := setupBenchmarkTestRouter(server.URL, "test-admin-key")

	// Corpo JSON invalido (falta target_endpoint)
	body := strings.NewReader(`{"concurrency": 1, "duration_seconds": 1}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/benchmark/load", body)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Admin-API-Key", "test-admin-key")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected status 400, got %d", w.Code)
	}
}

func TestBenchmarkLoadStatus_AfterCompletion_ReturnsReport(t *testing.T) {
	// Mock Python server com latencia controlada
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(10 * time.Millisecond) // Simular latencia
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"answer":"ok","sources":[],"session_id":"","created_at":"2024-01-01T00:00:00Z"}`))
	}))
	defer server.Close()

	r := setupBenchmarkTestRouter(server.URL, "test-admin-key")

	// Iniciar benchmark curto
	body := strings.NewReader(`{
		"target_endpoint": "chat",
		"concurrency": 2,
		"duration_seconds": 1,
		"payload": {"project_id":"00000000-0000-0000-0000-000000000001","session_id":"test","message":"ola"}
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/benchmark/load", body)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Admin-API-Key", "test-admin-key")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusAccepted {
		t.Fatalf("expected status 202, got %d", w.Code)
	}

	var acceptResp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &acceptResp); err != nil {
		t.Fatalf("failed to parse accept response: %v", err)
	}
	runID := acceptResp["run_id"].(string)

	// Aguardar benchmark completar (1s de duracao + margem)
	time.Sleep(3 * time.Second)

	// Consultar status
	req2 := httptest.NewRequest(http.MethodGet, "/api/v1/admin/benchmark/load/"+runID, nil)
	req2.Header.Set("X-Admin-API-Key", "test-admin-key")
	w2 := httptest.NewRecorder()
	r.ServeHTTP(w2, req2)

	if w2.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", w2.Code)
	}

	var report BenchmarkReport
	if err := json.Unmarshal(w2.Body.Bytes(), &report); err != nil {
		t.Fatalf("failed to parse report: %v", err)
	}

	if report.RunID != runID {
		t.Errorf("expected run_id %s, got %s", runID, report.RunID)
	}
	if report.Status != "completed" {
		t.Errorf("expected status 'completed', got %s", report.Status)
	}
	if report.TotalRequests == 0 {
		t.Error("expected total_requests > 0")
	}
	if report.Successful+report.Failed != report.TotalRequests {
		t.Errorf("successful + failed should equal total_requests")
	}
	if report.Throughput <= 0 {
		t.Error("expected throughput > 0")
	}
}

func TestInternalMetrics_ReturnsMetrics(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	r := setupBenchmarkTestRouter(server.URL, "test-admin-key")

	req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/metrics/internal", nil)
	req.Header.Set("X-Admin-API-Key", "test-admin-key")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	var metrics map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &metrics); err != nil {
		t.Fatalf("failed to parse metrics: %v", err)
	}

	// Verificar que circuit_breakers esta presente
	if _, ok := metrics["circuit_breakers"]; !ok {
		t.Error("expected circuit_breakers in metrics")
	}

	// Verificar que pdf_queue_depth esta presente
	if _, ok := metrics["pdf_queue_depth"]; !ok {
		t.Error("expected pdf_queue_depth in metrics")
	}

	// Verificar que cache_hit_ratio esta presente
	if _, ok := metrics["cache_hit_ratio"]; !ok {
		t.Error("expected cache_hit_ratio in metrics")
	}
}

func TestInternalMetrics_Unauthorized_Returns403(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	r := setupBenchmarkTestRouter(server.URL, "test-admin-key")

	req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/metrics/internal", nil)
	// Sem chave de administracao
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected status 403, got %d", w.Code)
	}
}

func TestBenchmarkLoad_EmptyAdminKey_AllowsAccess(t *testing.T) {
	// Quando adminKey e vazio, o middleware permite acesso sem autenticacao
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	r := setupBenchmarkTestRouter(server.URL, "") // chave vazia

	body := strings.NewReader(`{
		"target_endpoint": "chat",
		"concurrency": 1,
		"duration_seconds": 1,
		"payload": {"project_id":"00000000-0000-0000-0000-000000000001","session_id":"test","message":"ola"}
	}`)

	req := httptest.NewRequest(http.MethodPost, "/api/v1/admin/benchmark/load", body)
	req.Header.Set("Content-Type", "application/json")
	// Sem header X-Admin-API-Key
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// Deve permitir acesso (modo desenvolvimento)
	if w.Code != http.StatusAccepted {
		t.Errorf("expected status 202 with empty admin key, got %d", w.Code)
	}
}

func TestGetInternalMetrics_CacheHitRatio_ZeroWhenNoRequests(t *testing.T) {
	// Verificar que cache_hit_ratio e 0 quando nao ha requests
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	r := setupBenchmarkTestRouter(server.URL, "test-admin-key")

	req := httptest.NewRequest(http.MethodGet, "/api/v1/admin/metrics/internal", nil)
	req.Header.Set("X-Admin-API-Key", "test-admin-key")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	var metrics map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &metrics); err != nil {
		t.Fatalf("failed to parse metrics: %v", err)
	}

	hitRatio, ok := metrics["cache_hit_ratio"].(float64)
	if !ok {
		t.Fatal("expected cache_hit_ratio to be a number")
	}
	if hitRatio != 0 {
		t.Errorf("expected cache_hit_ratio 0 when no requests, got %f", hitRatio)
	}
}

// TestBenchmarkRunner_Direct testa o BenchmarkRunner diretamente sem router.
func TestBenchmarkRunner_Direct_GetStatusNotFound(t *testing.T) {
	client := python.NewClient("http://localhost:9999", nil, nil)
	runner := NewBenchmarkRunner(client)

	gin.SetMode(gin.TestMode)
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Params = gin.Params{{Key: "run_id", Value: "non-existent"}}

	handler := runner.GetBenchmarkStatus()
	handler(c)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected status 404, got %d", w.Code)
	}
}
