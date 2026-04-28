package python

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
)

func TestNewClient(t *testing.T) {
	url := "http://localhost:8000"
	timeout := 15 * time.Second

	client := NewClient(url, timeout)

	if client.BaseURL() != url {
		t.Errorf("expected baseURL %s, got %s", url, client.BaseURL())
	}
	if client.Timeout() != timeout {
		t.Errorf("expected timeout %s, got %s", timeout, client.Timeout())
	}
}

func TestClient_ProcessDocument_Mock(t *testing.T) {
	client := NewClient("http://localhost:8000", 30*time.Second)

	docID := uuid.New()
	req := &v1.ProcessDocumentRequest{
		ProjectID:  uuid.New(),
		DocumentID: docID,
		StorageKey: "s3://bucket/doc.pdf",
		SourceType: "user_upload",
	}

	ctx := context.Background()
	resp := client.ProcessDocument(ctx, req)

	if resp.DocumentID != docID {
		t.Errorf("expected DocumentID %s, got %s", docID, resp.DocumentID)
	}
	if resp.Status != "pending" {
		t.Errorf("expected status pending, got %s", resp.Status)
	}
	if resp.ChunksCount == nil {
		t.Error("expected ChunksCount to be set")
	}
}

func TestClient_Chat_Mock(t *testing.T) {
	client := NewClient("http://localhost:8000", 30*time.Second)

	req := &v1.ChatRequest{
		ProjectID: uuid.New(),
		SessionID: "test-session",
		Message:   "Ola, mundo",
	}

	ctx := context.Background()
	resp := client.Chat(ctx, req)

	if resp.Answer == "" {
		t.Error("expected non-empty Answer")
	}
	if resp.SessionID != req.SessionID {
		t.Errorf("expected SessionID %s, got %s", req.SessionID, resp.SessionID)
	}
	if resp.Sources == nil {
		t.Error("expected Sources slice (may be empty)")
	}
}

func TestClient_Summarize_Mock(t *testing.T) {
	client := NewClient("http://localhost:8000", 30*time.Second)

	docID := uuid.New()
	req := &v1.SummarizeRequest{
		DocumentID: docID,
		ProjectID:  uuid.New(),
		Format:     "structured",
	}

	ctx := context.Background()
	resp := client.Summarize(ctx, req)

	if resp.DocumentID != docID {
		t.Errorf("expected DocumentID %s, got %s", docID, resp.DocumentID)
	}
	if len(resp.Summary) == 0 {
		t.Error("expected non-empty Summary map")
	}
	// Verificar chaves esperadas
	for _, key := range []string{"objective", "methodology", "results", "conclusion"} {
		if _, ok := resp.Summary[key]; !ok {
			t.Errorf("expected Summary key %s", key)
		}
	}
}

func TestClient_Compare_Mock(t *testing.T) {
	client := NewClient("http://localhost:8000", 30*time.Second)

	projID := uuid.New()
	req := &v1.CompareRequest{
		ProjectID:   projID,
		DocumentIDs: []uuid.UUID{uuid.New(), uuid.New()},
		Theme:       "metodologia",
	}

	ctx := context.Background()
	resp := client.Compare(ctx, req)

	if resp.ProjectID != projID {
		t.Errorf("expected ProjectID %s, got %s", projID, resp.ProjectID)
	}
	if len(resp.Comparison) == 0 {
		t.Error("expected non-empty Comparison map")
	}
	if resp.Sources == nil {
		t.Error("expected Sources slice (may be empty)")
	}
}
