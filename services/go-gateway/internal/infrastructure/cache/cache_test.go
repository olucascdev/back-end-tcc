package cache

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
)

func TestNormalizeQuestion(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  string
	}{
		{
			name:  "trims spaces and lowercases",
			input: "  Hello World  ",
			want:  "hello world",
		},
		{
			name:  "removes punctuation",
			input: "WHAT??",
			want:  "what",
		},
		{
			name:  "collapses whitespace",
			input: "a   b\tc",
			want:  "a b c",
		},
		{
			name:  "removes special chars keeps digits",
			input: "123!@#",
			want:  "123",
		},
		{
			name:  "empty string",
			input: "",
			want:  "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := NormalizeQuestion(tt.input)
			if got != tt.want {
				t.Errorf("NormalizeQuestion(%q) = %q, want %q", tt.input, got, tt.want)
			}
		})
	}
}

func TestBuildCacheKey(t *testing.T) {
	projectID := uuid.MustParse("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
	question := "What is Go?"
	version := 1

	key := BuildCacheKey(projectID, question, version)

	// Must contain project UUID
	if !strings.Contains(key, projectID.String()) {
		t.Errorf("cache key %q missing project UUID %q", key, projectID.String())
	}

	// Must contain 16-char hex hash segment
	parts := strings.Split(key, ":")
	if len(parts) != 4 {
		t.Fatalf("expected 4 parts in key, got %d: %q", len(parts), key)
	}
	if parts[0] != "chat" {
		t.Errorf("expected prefix 'chat', got %q", parts[0])
	}
	hashPart := parts[2]
	if len(hashPart) != 16 {
		t.Errorf("expected hash length 16, got %d", len(hashPart))
	}
	for _, r := range hashPart {
		if !((r >= '0' && r <= '9') || (r >= 'a' && r <= 'f')) {
			t.Errorf("hash contains non-hex char %q", r)
			break
		}
	}

	// Must contain version
	if parts[3] != "1" {
		t.Errorf("expected version '1', got %q", parts[3])
	}

	// Deterministic: same inputs → same key
	key2 := BuildCacheKey(projectID, question, version)
	if key != key2 {
		t.Errorf("BuildCacheKey not deterministic: %q != %q", key, key2)
	}
}

func TestSemanticCache_Disabled(t *testing.T) {
	ctx := context.Background()
	sc := &SemanticCache{
		enabled: false,
	}

	// Get returns ErrCacheUnavailable
	_, err := sc.Get(ctx, "test-key")
	if err != ErrCacheUnavailable {
		t.Errorf("disabled Get: expected ErrCacheUnavailable, got %v", err)
	}

	// Set returns nil (fire-and-forget, no-op when disabled)
	resp := &v1.ChatResponse{Answer: "test"}
	err = sc.Set(ctx, "test-key", resp)
	if err != nil {
		t.Errorf("disabled Set: expected nil, got %v", err)
	}
}

func TestSemanticCache_NilClient(t *testing.T) {
	ctx := context.Background()
	sc := &SemanticCache{
		enabled:     true,
		redisClient: nil,
	}

	// Get returns ErrCacheUnavailable
	_, err := sc.Get(ctx, "test-key")
	if err != ErrCacheUnavailable {
		t.Errorf("nil client Get: expected ErrCacheUnavailable, got %v", err)
	}

	// Set returns nil (no-op when client is nil)
	resp := &v1.ChatResponse{Answer: "test"}
	err = sc.Set(ctx, "test-key", resp)
	if err != nil {
		t.Errorf("nil client Set: expected nil, got %v", err)
	}
}

func TestSemanticCache_GetProjectCacheVersion_Disabled(t *testing.T) {
	ctx := context.Background()
	sc := &SemanticCache{
		enabled: false,
	}

	// Cache desabilitado retorna 0, nil (no-op)
	version, err := sc.GetProjectCacheVersion(ctx, "test-project")
	if err != nil {
		t.Errorf("disabled GetProjectCacheVersion: expected nil error, got %v", err)
	}
	if version != 0 {
		t.Errorf("disabled GetProjectCacheVersion: expected version 0, got %d", version)
	}
}

func TestSemanticCache_GetProjectCacheVersion_NilClient(t *testing.T) {
	ctx := context.Background()
	sc := &SemanticCache{
		enabled:     true,
		redisClient: nil,
	}

	// Client nil retorna 0, nil (no-op)
	version, err := sc.GetProjectCacheVersion(ctx, "test-project")
	if err != nil {
		t.Errorf("nil client GetProjectCacheVersion: expected nil error, got %v", err)
	}
	if version != 0 {
		t.Errorf("nil client GetProjectCacheVersion: expected version 0, got %d", version)
	}
}

func TestSemanticCache_IncrementProjectCacheVersion_Disabled(t *testing.T) {
	ctx := context.Background()
	sc := &SemanticCache{
		enabled: false,
	}

	// Cache desabilitado retorna 0, nil (no-op)
	version, err := sc.IncrementProjectCacheVersion(ctx, "test-project")
	if err != nil {
		t.Errorf("disabled IncrementProjectCacheVersion: expected nil error, got %v", err)
	}
	if version != 0 {
		t.Errorf("disabled IncrementProjectCacheVersion: expected version 0, got %d", version)
	}
}

func TestSemanticCache_IncrementProjectCacheVersion_NilClient(t *testing.T) {
	ctx := context.Background()
	sc := &SemanticCache{
		enabled:     true,
		redisClient: nil,
	}

	// Client nil retorna 0, nil (no-op)
	version, err := sc.IncrementProjectCacheVersion(ctx, "test-project")
	if err != nil {
		t.Errorf("nil client IncrementProjectCacheVersion: expected nil error, got %v", err)
	}
	if version != 0 {
		t.Errorf("nil client IncrementProjectCacheVersion: expected version 0, got %d", version)
	}
}
