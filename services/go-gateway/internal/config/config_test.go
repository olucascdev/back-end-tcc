package config

import (
	"os"
	"testing"
	"time"
)

func TestLoadConfig_Defaults(t *testing.T) {
	// Limpar variaveis de ambiente relevantes para testar defaults
	envVars := []string{
		"GO_GATEWAY_PORT", "PYTHON_AGENT_URL", "REDIS_URL", "DB_URL",
		"MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "REQUEST_TIMEOUT",
	}
	for _, v := range envVars {
		os.Unsetenv(v)
	}

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
	if cfg.RequestTimeout != 30*time.Second {
		t.Errorf("expected RequestTimeout 30s, got %s", cfg.RequestTimeout)
	}
}

func TestLoadConfig_EnvOverrides(t *testing.T) {
	os.Setenv("GO_GATEWAY_PORT", "9090")
	os.Setenv("PYTHON_AGENT_URL", "http://agent:8000")
	os.Setenv("REQUEST_TIMEOUT", "60s")
	defer func() {
		os.Unsetenv("GO_GATEWAY_PORT")
		os.Unsetenv("PYTHON_AGENT_URL")
		os.Unsetenv("REQUEST_TIMEOUT")
	}()

	cfg := LoadConfig()

	if cfg.ServerPort != "9090" {
		t.Errorf("expected ServerPort 9090, got %s", cfg.ServerPort)
	}
	if cfg.PythonAgentURL != "http://agent:8000" {
		t.Errorf("expected PythonAgentURL http://agent:8000, got %s", cfg.PythonAgentURL)
	}
	if cfg.RequestTimeout != 60*time.Second {
		t.Errorf("expected RequestTimeout 60s, got %s", cfg.RequestTimeout)
	}
}

func TestParseDuration_Invalid(t *testing.T) {
	// parseDuration e interna, testamos indiretamente via LoadConfig
	os.Setenv("REQUEST_TIMEOUT", "invalid")
	defer os.Unsetenv("REQUEST_TIMEOUT")

	cfg := LoadConfig()

	// Deve fallback para 30s quando valor invalido
	if cfg.RequestTimeout != 30*time.Second {
		t.Errorf("expected fallback 30s for invalid duration, got %s", cfg.RequestTimeout)
	}
}
