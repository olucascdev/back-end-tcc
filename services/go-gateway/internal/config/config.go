// Package config carrega configuracoes do gateway a partir de variaveis de
// ambiente com valores padrao para desenvolvimento local.
package config

import (
	"os"
	"time"
)

// Config contem todas as configuracoes necessarias para o gateway.
type Config struct {
	ServerPort     string
	PythonAgentURL string
	RedisURL       string
	DatabaseURL    string
	MinioEndpoint  string
	MinioAccessKey string
	MinioSecretKey string
	RequestTimeout time.Duration
}

// LoadConfig carrega configuracoes de variaveis de ambiente com defaults.
func LoadConfig() *Config {
	return &Config{
		ServerPort:     getEnv("GO_GATEWAY_PORT", "8080"),
		PythonAgentURL: getEnv("PYTHON_AGENT_URL", "http://localhost:8000"),
		RedisURL:       getEnv("REDIS_URL", "redis://localhost:6379/0"),
		DatabaseURL:    getEnv("DB_URL", "postgres://localhost:5432/tcc_db"),
		MinioEndpoint:  getEnv("MINIO_ENDPOINT", "localhost:9000"),
		MinioAccessKey: getEnv("MINIO_ACCESS_KEY", "minioadmin"),
		MinioSecretKey: getEnv("MINIO_SECRET_KEY", "minioadmin"),
		RequestTimeout: parseDuration(getEnv("REQUEST_TIMEOUT", "30s")),
	}
}

// getEnv retorna o valor da variavel de ambiente ou o default se nao definida.
func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

// parseDuration converte string para time.Duration com fallback para default.
func parseDuration(val string) time.Duration {
	d, err := time.ParseDuration(val)
	if err != nil {
		return 30 * time.Second
	}
	return d
}
