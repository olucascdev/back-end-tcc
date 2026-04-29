package config

import (
	"os"
	"testing"
	"time"
)

// envVars lista todas as variaveis de ambiente usadas pelo config.
var envVars = []string{
	"GO_GATEWAY_PORT", "PYTHON_AGENT_URL", "REDIS_URL", "DB_URL",
	"MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY",
	"REQUEST_TIMEOUT",
	"TIMEOUT_CHAT", "TIMEOUT_SUMMARIZE", "TIMEOUT_COMPARE",
	"TIMEOUT_PROCESS_DOCUMENT", "TIMEOUT_HEALTH",
}

// clearEnvVars limpa todas as variaveis de ambiente relevantes.
func clearEnvVars() {
	for _, v := range envVars {
		os.Unsetenv(v)
	}
}

func TestLoadConfig_Defaults(t *testing.T) {
	clearEnvVars()

	cfg := LoadConfig()

	if cfg.ServerPort != "8080" {
		t.Errorf("expected ServerPort 8080, got %s", cfg.ServerPort)
	}
	if cfg.PythonAgentURL != "http://localhost:8000" {
		t.Errorf("expected PythonAgentURL http://localhost:8000, got %s", cfg.PythonAgentURL)
	}
	if cfg.RedisURL != "redis://localhost:6379/0" {
		t.Errorf("expected RedisURL redis://localhost:6379/0, got %s", cfg.RedisURL)
	}
	if cfg.DatabaseURL != "postgres://localhost:5432/tcc_db" {
		t.Errorf("expected DatabaseURL postgres://localhost:5432/tcc_db, got %s", cfg.DatabaseURL)
	}
	if cfg.MinioEndpoint != "localhost:9000" {
		t.Errorf("expected MinioEndpoint localhost:9000, got %s", cfg.MinioEndpoint)
	}
	if cfg.MinioAccessKey != "minioadmin" {
		t.Errorf("expected MinioAccessKey minioadmin, got %s", cfg.MinioAccessKey)
	}
	if cfg.MinioSecretKey != "minioadmin" {
		t.Errorf("expected MinioSecretKey minioadmin, got %s", cfg.MinioSecretKey)
	}
}

func TestLoadConfig_DefaultTimeoutsPerOperation(t *testing.T) {
	clearEnvVars()

	cfg := LoadConfig()

	// Defaults por operacao quando nenhuma env var esta definida
	if cfg.TimeoutChat != 30*time.Second {
		t.Errorf("expected TimeoutChat 30s, got %s", cfg.TimeoutChat)
	}
	if cfg.TimeoutSummarize != 30*time.Second {
		t.Errorf("expected TimeoutSummarize 30s, got %s", cfg.TimeoutSummarize)
	}
	if cfg.TimeoutCompare != 30*time.Second {
		t.Errorf("expected TimeoutCompare 30s, got %s", cfg.TimeoutCompare)
	}
	if cfg.TimeoutProcessDocument != 60*time.Second {
		t.Errorf("expected TimeoutProcessDocument 60s, got %s", cfg.TimeoutProcessDocument)
	}
	if cfg.TimeoutHealth != 5*time.Second {
		t.Errorf("expected TimeoutHealth 5s, got %s", cfg.TimeoutHealth)
	}
}

func TestLoadConfig_EnvOverrides(t *testing.T) {
	clearEnvVars()

	os.Setenv("GO_GATEWAY_PORT", "9090")
	os.Setenv("PYTHON_AGENT_URL", "http://agent:8000")
	defer clearEnvVars()

	cfg := LoadConfig()

	if cfg.ServerPort != "9090" {
		t.Errorf("expected ServerPort 9090, got %s", cfg.ServerPort)
	}
	if cfg.PythonAgentURL != "http://agent:8000" {
		t.Errorf("expected PythonAgentURL http://agent:8000, got %s", cfg.PythonAgentURL)
	}
}

func TestLoadConfig_PerOperationTimeoutOverrides(t *testing.T) {
	clearEnvVars()

	os.Setenv("TIMEOUT_CHAT", "45s")
	os.Setenv("TIMEOUT_SUMMARIZE", "20s")
	os.Setenv("TIMEOUT_COMPARE", "50s")
	os.Setenv("TIMEOUT_PROCESS_DOCUMENT", "120s")
	os.Setenv("TIMEOUT_HEALTH", "3s")
	defer clearEnvVars()

	cfg := LoadConfig()

	if cfg.TimeoutChat != 45*time.Second {
		t.Errorf("expected TimeoutChat 45s, got %s", cfg.TimeoutChat)
	}
	if cfg.TimeoutSummarize != 20*time.Second {
		t.Errorf("expected TimeoutSummarize 20s, got %s", cfg.TimeoutSummarize)
	}
	if cfg.TimeoutCompare != 50*time.Second {
		t.Errorf("expected TimeoutCompare 50s, got %s", cfg.TimeoutCompare)
	}
	if cfg.TimeoutProcessDocument != 120*time.Second {
		t.Errorf("expected TimeoutProcessDocument 120s, got %s", cfg.TimeoutProcessDocument)
	}
	if cfg.TimeoutHealth != 3*time.Second {
		t.Errorf("expected TimeoutHealth 3s, got %s", cfg.TimeoutHealth)
	}
}

func TestLoadConfig_GlobalTimeoutFallback(t *testing.T) {
	clearEnvVars()

	// Definir apenas REQUEST_TIMEOUT — deve ser usado como fallback
	os.Setenv("REQUEST_TIMEOUT", "45s")
	defer clearEnvVars()

	cfg := LoadConfig()

	// Todos os timeouts devem herdar o fallback de 45s
	if cfg.TimeoutChat != 45*time.Second {
		t.Errorf("expected TimeoutChat 45s (fallback), got %s", cfg.TimeoutChat)
	}
	if cfg.TimeoutSummarize != 45*time.Second {
		t.Errorf("expected TimeoutSummarize 45s (fallback), got %s", cfg.TimeoutSummarize)
	}
	if cfg.TimeoutCompare != 45*time.Second {
		t.Errorf("expected TimeoutCompare 45s (fallback), got %s", cfg.TimeoutCompare)
	}
	if cfg.TimeoutProcessDocument != 45*time.Second {
		t.Errorf("expected TimeoutProcessDocument 45s (fallback), got %s", cfg.TimeoutProcessDocument)
	}
	if cfg.TimeoutHealth != 45*time.Second {
		t.Errorf("expected TimeoutHealth 45s (fallback), got %s", cfg.TimeoutHealth)
	}
}

func TestLoadConfig_SpecificOverridesGlobalFallback(t *testing.T) {
	clearEnvVars()

	// REQUEST_TIMEOUT como fallback + override especifico
	os.Setenv("REQUEST_TIMEOUT", "45s")
	os.Setenv("TIMEOUT_CHAT", "15s")
	defer clearEnvVars()

	cfg := LoadConfig()

	// TIMEOUT_CHAT deve usar valor especifico, nao fallback
	if cfg.TimeoutChat != 15*time.Second {
		t.Errorf("expected TimeoutChat 15s (specific override), got %s", cfg.TimeoutChat)
	}
	// Demais devem usar fallback
	if cfg.TimeoutSummarize != 45*time.Second {
		t.Errorf("expected TimeoutSummarize 45s (fallback), got %s", cfg.TimeoutSummarize)
	}
}

func TestParseDuration_Invalid(t *testing.T) {
	clearEnvVars()

	os.Setenv("REQUEST_TIMEOUT", "invalid")
	defer clearEnvVars()

	cfg := LoadConfig()

	// Deve fallback para 30s quando valor invalido
	if cfg.TimeoutChat != 30*time.Second {
		t.Errorf("expected fallback 30s for invalid duration, got %s", cfg.TimeoutChat)
	}
}

func TestParseDurationWithFallback_InvalidSpecific(t *testing.T) {
	clearEnvVars()

	os.Setenv("TIMEOUT_CHAT", "invalid")
	os.Setenv("REQUEST_TIMEOUT", "20s")
	defer clearEnvVars()

	cfg := LoadConfig()

	// Timeout especifico invalido → usa fallback REQUEST_TIMEOUT
	if cfg.TimeoutChat != 20*time.Second {
		t.Errorf("expected fallback 20s for invalid specific timeout, got %s", cfg.TimeoutChat)
	}
}
