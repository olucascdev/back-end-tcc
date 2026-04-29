// Package config carrega configuracoes do gateway a partir de variaveis de
// ambiente com valores padrao para desenvolvimento local.
package config

import (
	"os"
	"strconv"
	"strings"
	"time"
)

// Config contem todas as configuracoes necessarias para o gateway.
type Config struct {
	ServerPort                  string
	PythonAgentURL              string
	RedisURL                    string
	DatabaseURL                 string
	MinioEndpoint               string
	MinioAccessKey              string
	MinioSecretKey              string
	TimeoutChat                 time.Duration
	TimeoutSummarize            time.Duration
	TimeoutCompare              time.Duration
	TimeoutProcessDocument      time.Duration
	TimeoutHealth               time.Duration
	CircuitMaxRequests          uint32
	CircuitFailureThreshold     uint32
	CircuitTimeout              time.Duration
	RetryMaxRetries             int
	RetryBaseDelay              time.Duration
	RetryMaxDelay               time.Duration
	RateLimitRequests           int
	RateLimitBurst              int
	PDFWorkers                  int
	PDFQueueSize                int
	WebhookURL                  string
	WebhookSecret               string
	CacheTTL                    time.Duration
	CacheEnabled                bool
}

// LoadConfig carrega configuracoes de variaveis de ambiente com defaults.
// Suporta backward compat: REQUEST_TIMEOUT serve como fallback global quando
// os timeouts especificos nao estao definidos.
func LoadConfig() *Config {
	// Fallback global para backward compat (apenas se REQUEST_TIMEOUT estiver definido)
	rawGlobal := getEnv("REQUEST_TIMEOUT", "")
	var globalTimeout time.Duration
	if rawGlobal != "" {
		globalTimeout = parseDuration(rawGlobal)
	}

	return &Config{
		ServerPort:             getEnv("GO_GATEWAY_PORT", "8080"),
		PythonAgentURL:         getEnv("PYTHON_AGENT_URL", "http://localhost:8000"),
		RedisURL:               getEnv("REDIS_URL", "redis://localhost:6379/0"),
		DatabaseURL:            getEnv("DB_URL", "postgres://localhost:5432/tcc_db"),
		MinioEndpoint:          getEnv("MINIO_ENDPOINT", "localhost:9000"),
		MinioAccessKey:         getEnv("MINIO_ACCESS_KEY", "minioadmin"),
		MinioSecretKey:         getEnv("MINIO_SECRET_KEY", "minioadmin"),
		TimeoutChat:            parseDurationWithFallback(getEnv("TIMEOUT_CHAT", ""), globalTimeout, 30*time.Second),
		TimeoutSummarize:       parseDurationWithFallback(getEnv("TIMEOUT_SUMMARIZE", ""), globalTimeout, 30*time.Second),
		TimeoutCompare:         parseDurationWithFallback(getEnv("TIMEOUT_COMPARE", ""), globalTimeout, 30*time.Second),
		TimeoutProcessDocument: parseDurationWithFallback(getEnv("TIMEOUT_PROCESS_DOCUMENT", ""), globalTimeout, 60*time.Second),
		TimeoutHealth:          parseDurationWithFallback(getEnv("TIMEOUT_HEALTH", ""), globalTimeout, 5*time.Second),
		CircuitMaxRequests:     parseUint32(getEnv("CIRCUIT_MAX_REQUESTS", "3")),
		CircuitFailureThreshold: parseUint32(getEnv("CIRCUIT_FAILURE_THRESHOLD", "5")),
		CircuitTimeout:         parseDurationWithFallback(getEnv("CIRCUIT_TIMEOUT", ""), 0, 30*time.Second),
		RetryMaxRetries:        parseInt(getEnv("RETRY_MAX_RETRIES", "3")),
		RetryBaseDelay:         parseDuration(getEnv("RETRY_BASE_DELAY", "100ms")),
		RetryMaxDelay:          parseDuration(getEnv("RETRY_MAX_DELAY", "2s")),
		RateLimitRequests:      parseInt(getEnv("RATE_LIMIT_REQUESTS", "10")),
		RateLimitBurst:         parseInt(getEnv("RATE_LIMIT_BURST", "20")),
		PDFWorkers:             parseInt(getEnv("PDF_WORKERS", "3")),
		PDFQueueSize:           parseInt(getEnv("PDF_QUEUE_SIZE", "100")),
		WebhookURL:             getEnv("WEBHOOK_URL", ""),
		WebhookSecret:          getEnv("WEBHOOK_SECRET", ""),
		CacheTTL:               parseDurationWithFallback(getEnv("CACHE_TTL", ""), 0, 5*time.Minute),
		CacheEnabled:           parseBool(getEnv("CACHE_ENABLED", "true")),
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

// parseDurationWithFallback tenta parsear o valor; se vazio ou invalido,
// usa fallback (geralmente REQUEST_TIMEOUT); se tambem zero, usa defaultOp.
func parseDurationWithFallback(val string, fallback time.Duration, defaultOp time.Duration) time.Duration {
	if val == "" {
		if fallback > 0 {
			return fallback
		}
		return defaultOp
	}
	d, err := time.ParseDuration(val)
	if err != nil {
		if fallback > 0 {
			return fallback
		}
		return defaultOp
	}
	return d
}

// parseUint32 converte string para uint32 com fallback para default.
// Se a string for vazia ou invalida, retorna o valor default.
func parseUint32(val string) uint32 {
	if val == "" {
		return 0
	}
	n, err := strconv.ParseUint(val, 10, 32)
	if err != nil {
		return 0
	}
	return uint32(n)
}

// parseInt converte string para int com fallback para default.
// Se a string for vazia ou invalida, retorna o valor default.
func parseInt(val string) int {
	if val == "" {
		return 0
	}
	n, err := strconv.Atoi(val)
	if err != nil {
		return 0
	}
	return n
}

// parseBool converte string para bool com fallback para default.
// Valores verdadeiros: "true", "1", "yes", "on" (case-insensitive).
func parseBool(val string) bool {
	if val == "" {
		return true // default: cache habilitado
	}
	lower := strings.ToLower(val)
	return lower == "true" || lower == "1" || lower == "yes" || lower == "on"
}
