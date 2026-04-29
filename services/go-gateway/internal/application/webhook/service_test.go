package webhook

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
)

func TestService_SendWebhookSuccess(t *testing.T) {
	var receivedBody v1.DocumentStatusWebhook
	var receivedSignature, receivedIdempotencyKey string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Validar metodo
		if r.Method != http.MethodPost {
			t.Errorf("expected POST request, got %s", r.Method)
		}

		// Validar Content-Type
		if ct := r.Header.Get("Content-Type"); ct != "application/json" {
			t.Errorf("expected Content-Type application/json, got %s", ct)
		}

		// Capturar headers
		receivedSignature = r.Header.Get("X-Webhook-Signature")
		receivedIdempotencyKey = r.Header.Get("X-Idempotency-Key")

		// Ler e deserializar body
		bodyBytes, err := io.ReadAll(r.Body)
		if err != nil {
			t.Fatalf("failed to read request body: %v", err)
		}
		if err := json.Unmarshal(bodyBytes, &receivedBody); err != nil {
			t.Fatalf("failed to unmarshal request body: %v", err)
		}

		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	svc := NewService(server.URL, "test-secret")

	docID := uuid.New()
	projID := uuid.New()
	payload := &v1.DocumentStatusWebhook{
		DocumentID: docID,
		ProjectID:  projID,
		Status:     "ready",
		Timestamp:  time.Now(),
	}

	err := svc.SendWebhook(payload)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	// Validar payload recebido
	if receivedBody.DocumentID != docID {
		t.Errorf("expected document_id %s, got %s", docID, receivedBody.DocumentID)
	}
	if receivedBody.Status != "ready" {
		t.Errorf("expected status ready, got %s", receivedBody.Status)
	}

	// Validar idempotency key
	if receivedIdempotencyKey != docID.String() {
		t.Errorf("expected idempotency key %s, got %s", docID.String(), receivedIdempotencyKey)
	}

	// Validar assinatura
	if receivedSignature == "" {
		t.Error("expected X-Webhook-Signature header to be present")
	}
}

func TestService_SendWebhookInvalidStatus(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	svc := NewService(server.URL, "test-secret")

	payload := &v1.DocumentStatusWebhook{
		DocumentID: uuid.New(),
		ProjectID:  uuid.New(),
		Status:     "error",
		Timestamp:  time.Now(),
	}

	err := svc.SendWebhook(payload)
	if err == nil {
		t.Fatal("expected error for 500 response, got nil")
	}
}

func TestService_SendWebhookSignature(t *testing.T) {
	secret := "my-secret-key"
	var receivedSignature string
	var receivedBody []byte

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedSignature = r.Header.Get("X-Webhook-Signature")
		receivedBody, _ = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	svc := NewService(server.URL, secret)

	payload := &v1.DocumentStatusWebhook{
		DocumentID: uuid.New(),
		ProjectID:  uuid.New(),
		Status:     "ready",
		Timestamp:  time.Now(),
	}

	err := svc.SendWebhook(payload)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}

	// Calcular assinatura esperada
	expectedMAC := hmac.New(sha256.New, []byte(secret))
	expectedMAC.Write(receivedBody)
	expectedSignature := "sha256=" + hex.EncodeToString(expectedMAC.Sum(nil))

	if receivedSignature != expectedSignature {
		t.Errorf("expected signature %s, got %s", expectedSignature, receivedSignature)
	}
}

func TestService_SendWebhookDisabled(t *testing.T) {
	// URL vazia deve retornar nil sem enviar nada
	svc := NewService("", "test-secret")

	if svc.IsEnabled() {
		t.Error("expected webhook to be disabled with empty URL")
	}

	payload := &v1.DocumentStatusWebhook{
		DocumentID: uuid.New(),
		ProjectID:  uuid.New(),
		Status:     "ready",
		Timestamp:  time.Now(),
	}

	err := svc.SendWebhook(payload)
	if err != nil {
		t.Fatalf("expected no error when webhook is disabled, got %v", err)
	}
}
