// Package webhook fornece servico de notificacao via HTTP webhook
// com assinatura HMAC-SHA256 e chave de idempotencia.
package webhook

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
)

// Metricas Prometheus para webhook.
var (
	// webhookSentTotal — total de webhooks enviados por status.
	webhookSentTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "webhook_sent_total",
			Help: "Total number of webhooks sent by delivery status",
		},
		[]string{"status"},
	)

	// webhookDuration — latencia de envio de webhook.
	webhookDuration = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "webhook_duration_seconds",
			Help:    "Latency of webhook delivery in seconds",
			Buckets: prometheus.DefBuckets,
		},
	)
)

// Service envia notificacoes de status de documento para um endpoint webhook.
// Usa HMAC-SHA256 para assinar o payload e header de idempotencia para
// garantir entregas idempotentes.
type Service struct {
	webhookURL string
	secret     string
	httpClient *http.Client
}

// NewService cria um novo servico de webhook.
// Se webhookURL for vazio, o servico e considerado desabilitado.
func NewService(webhookURL, secret string) *Service {
	return &Service{
		webhookURL: webhookURL,
		secret:     secret,
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

// IsEnabled retorna true se o webhook esta configurado com URL valida.
func (s *Service) IsEnabled() bool {
	return s.webhookURL != ""
}

// SendWebhook envia o payload de status de documento para o endpoint configurado.
// Gera assinatura HMAC-SHA256 do body e inclui chave de idempotencia baseada no job_id.
// Retorna erro se o servidor responder com status >= 400 ou houver falha de rede.
func (s *Service) SendWebhook(payload *v1.DocumentStatusWebhook) error {
	if !s.IsEnabled() {
		return nil
	}

	start := time.Now()

	// Serializar payload para JSON
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal webhook payload: %w", err)
	}

	// Gerar assinatura HMAC-SHA256 do body
	signature := generateHMACSignature(body, s.secret)

	// Criar request POST para o webhook URL
	req, err := http.NewRequest(http.MethodPost, s.webhookURL, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("failed to create webhook request: %w", err)
	}

	// Definir headers obrigatorios
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Webhook-Signature", "sha256="+signature)
	req.Header.Set("X-Idempotency-Key", payload.DocumentID.String())

	// Enviar request
	resp, err := s.httpClient.Do(req)
	if err != nil {
		// Registrar metrica de falha
		webhookSentTotal.WithLabelValues("failure").Inc()
		webhookDuration.Observe(time.Since(start).Seconds())
		return fmt.Errorf("failed to send webhook request: %w", err)
	}
	defer resp.Body.Close()

	// Log estruturado de envio
	slog.Info("webhook sent",
		slog.String("document_id", payload.DocumentID.String()),
		slog.String("status", payload.Status),
		slog.Int("http_status", resp.StatusCode),
		slog.String("url", s.webhookURL),
	)

	// Observar duracao do envio
	webhookDuration.Observe(time.Since(start).Seconds())

	// Se status >= 400, registrar falha e retornar erro para permitir retry
	if resp.StatusCode >= 400 {
		webhookSentTotal.WithLabelValues("failure").Inc()
		return fmt.Errorf("webhook returned error status: %d", resp.StatusCode)
	}

	// Registrar sucesso
	webhookSentTotal.WithLabelValues("success").Inc()
	return nil
}

// generateHMACSignature gera assinatura HMAC-SHA256 do body usando o secret.
// Retorna a assinatura em formato hexadecimal.
func generateHMACSignature(body []byte, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}
