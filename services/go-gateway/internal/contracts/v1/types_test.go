package v1

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/google/uuid"
)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

func newUUID() uuid.UUID {
	return uuid.New()
}

func strPtr(s string) *string {
	return &s
}

func intPtr(i int) *int {
	return &i
}

// ---------------------------------------------------------------------------
// Source
// ---------------------------------------------------------------------------

func TestSource_JSONRoundTrip(t *testing.T) {
	s := Source{Document: "doc.pdf", Page: 3, Section: strPtr("Intro"), Score: 0.92}
	data, err := json.Marshal(s)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var s2 Source
	if err := json.Unmarshal(data, &s2); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if s2.Document != s.Document || s2.Page != s.Page || *s2.Section != *s.Section || s2.Score != s.Score {
		t.Errorf("roundtrip mismatch: got %+v, want %+v", s2, s)
	}
}

func TestSource_OmitEmptySection(t *testing.T) {
	s := Source{Document: "doc.pdf", Page: 1, Score: 0.5}
	data, _ := json.Marshal(s)

	var m map[string]interface{}
	json.Unmarshal(data, &m)

	if _, ok := m["section"]; ok {
		t.Error("section should be omitted when nil")
	}
}

// ---------------------------------------------------------------------------
// ProcessDocumentRequest
// ---------------------------------------------------------------------------

func TestProcessDocumentRequest_JSONRoundTrip(t *testing.T) {
	req := ProcessDocumentRequest{
		ProjectID:  newUUID(),
		DocumentID: newUUID(),
		StorageKey: "s3://bucket/key",
		SourceType: "user_upload",
	}
	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var req2 ProcessDocumentRequest
	if err := json.Unmarshal(data, &req2); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if req2.StorageKey != req.StorageKey {
		t.Errorf("storage_key mismatch")
	}
}

func TestProcessDocumentRequest_RequiredFields(t *testing.T) {
	// UUID zero-value still serializes; we validate presence at application layer.
	// This test ensures the struct can hold all required fields.
	req := ProcessDocumentRequest{
		ProjectID:  newUUID(),
		DocumentID: newUUID(),
		StorageKey: "key",
	}
	if req.ProjectID == uuid.Nil || req.DocumentID == uuid.Nil || req.StorageKey == "" {
		t.Error("required fields should not be zero")
	}
}

// ---------------------------------------------------------------------------
// ProcessDocumentResponse
// ---------------------------------------------------------------------------

func TestProcessDocumentResponse_JSONRoundTrip(t *testing.T) {
	now := time.Now().UTC()
	resp := ProcessDocumentResponse{
		DocumentID:  newUUID(),
		Status:      "ready",
		ChunksCount: intPtr(42),
		ProcessedAt: &now,
	}
	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var resp2 ProcessDocumentResponse
	if err := json.Unmarshal(data, &resp2); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if resp2.Status != resp.Status || *resp2.ChunksCount != *resp.ChunksCount {
		t.Errorf("roundtrip mismatch")
	}
}

func TestProcessDocumentResponse_OmitEmpty(t *testing.T) {
	resp := ProcessDocumentResponse{DocumentID: newUUID(), Status: "pending"}
	data, _ := json.Marshal(resp)

	var m map[string]interface{}
	json.Unmarshal(data, &m)

	for _, key := range []string{"chunks_count", "processed_at", "error_message"} {
		if _, ok := m[key]; ok {
			t.Errorf("%s should be omitted when nil", key)
		}
	}
}

// ---------------------------------------------------------------------------
// ChatRequest
// ---------------------------------------------------------------------------

func TestChatRequest_JSONRoundTrip(t *testing.T) {
	req := ChatRequest{
		ProjectID: newUUID(),
		SessionID: "sess-1",
		Message:   "Ola",
	}
	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var req2 ChatRequest
	if err := json.Unmarshal(data, &req2); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if req2.Message != req.Message {
		t.Errorf("message mismatch")
	}
}

func TestChatRequest_RequiredFields(t *testing.T) {
	req := ChatRequest{ProjectID: newUUID(), SessionID: "s", Message: "hi"}
	if req.SessionID == "" || req.Message == "" {
		t.Error("required fields should not be empty")
	}
}

// ---------------------------------------------------------------------------
// ChatResponse
// ---------------------------------------------------------------------------

func TestChatResponse_JSONRoundTrip(t *testing.T) {
	resp := ChatResponse{
		Answer:    "Sim.",
		Sources:   []Source{{Document: "doc.pdf", Page: 1, Score: 0.9}},
		SessionID: "sess-1",
		CreatedAt: time.Now().UTC(),
	}
	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var resp2 ChatResponse
	if err := json.Unmarshal(data, &resp2); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if resp2.Answer != resp.Answer || len(resp2.Sources) != 1 {
		t.Errorf("roundtrip mismatch")
	}
}

// ---------------------------------------------------------------------------
// SummarizeRequest
// ---------------------------------------------------------------------------

func TestSummarizeRequest_JSONRoundTrip(t *testing.T) {
	req := SummarizeRequest{
		DocumentID: newUUID(),
		ProjectID:  newUUID(),
		Format:     "structured",
	}
	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var req2 SummarizeRequest
	if err := json.Unmarshal(data, &req2); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if req2.Format != req.Format {
		t.Errorf("format mismatch")
	}
}

// ---------------------------------------------------------------------------
// SummarizeResponse
// ---------------------------------------------------------------------------

func TestSummarizeResponse_JSONRoundTrip(t *testing.T) {
	resp := SummarizeResponse{
		DocumentID: newUUID(),
		Summary: map[string]string{
			"objective":    "X",
			"methodology":  "Y",
			"results":      "Z",
			"conclusion":   "W",
		},
		CreatedAt: time.Now().UTC(),
	}
	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var resp2 SummarizeResponse
	if err := json.Unmarshal(data, &resp2); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if resp2.Summary["objective"] != "X" {
		t.Errorf("summary mismatch")
	}
}

// ---------------------------------------------------------------------------
// CompareRequest
// ---------------------------------------------------------------------------

func TestCompareRequest_JSONRoundTrip(t *testing.T) {
	req := CompareRequest{
		ProjectID:   newUUID(),
		DocumentIDs: []uuid.UUID{newUUID(), newUUID()},
		Theme:       "metodologia",
	}
	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var req2 CompareRequest
	if err := json.Unmarshal(data, &req2); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if len(req2.DocumentIDs) != 2 || req2.Theme != req.Theme {
		t.Errorf("roundtrip mismatch")
	}
}

// ---------------------------------------------------------------------------
// CompareResponse
// ---------------------------------------------------------------------------

func TestCompareResponse_JSONRoundTrip(t *testing.T) {
	resp := CompareResponse{
		ProjectID:  newUUID(),
		Comparison: map[string]string{"doc1": "A", "doc2": "B"},
		Sources:    []Source{{Document: "doc.pdf", Page: 1, Score: 0.8}},
		CreatedAt:  time.Now().UTC(),
	}
	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var resp2 CompareResponse
	if err := json.Unmarshal(data, &resp2); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if resp2.Comparison["doc1"] != "A" {
		t.Errorf("comparison mismatch")
	}
}

// ---------------------------------------------------------------------------
// DocumentStatusWebhook
// ---------------------------------------------------------------------------

func TestDocumentStatusWebhook_JSONRoundTrip(t *testing.T) {
	now := time.Now().UTC()
	wh := DocumentStatusWebhook{
		DocumentID: newUUID(),
		ProjectID:  newUUID(),
		Status:     "ready",
		Timestamp:  now,
	}
	data, err := json.Marshal(wh)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var wh2 DocumentStatusWebhook
	if err := json.Unmarshal(data, &wh2); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if wh2.Status != wh.Status {
		t.Errorf("status mismatch")
	}
}

func TestDocumentStatusWebhook_OmitEmpty(t *testing.T) {
	wh := DocumentStatusWebhook{
		DocumentID: newUUID(),
		ProjectID:  newUUID(),
		Status:     "processing",
		Timestamp:  time.Now().UTC(),
	}
	data, _ := json.Marshal(wh)

	var m map[string]interface{}
	json.Unmarshal(data, &m)

	for _, key := range []string{"error_message", "metadata"} {
		if _, ok := m[key]; ok {
			t.Errorf("%s should be omitted when nil", key)
		}
	}
}
