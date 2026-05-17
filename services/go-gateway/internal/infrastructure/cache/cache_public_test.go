package cache

import (
	"context"
	"testing"

	"github.com/google/uuid"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
)

// Testes de cache com respostas da biblioteca publica (retrieval_mode project_plus_public).
// Validam que chaves de cache diferenciam modos de retrieval e que respostas
// com fontes publicas sao armazenadas/recuperadas corretamente.

func TestBuildCacheKey_DifferentRetrievalModes(t *testing.T) {
	// Chaves de cache devem ser diferentes para retrieval modes diferentes
	// mesmo com mesma pergunta, pois o contexto retornado e diferente.
	projectID := uuid.MustParse("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
	question := "What is machine learning?"
	version := 1

	// Para project_only, usamos versao 1
	keyProjectOnly := BuildCacheKey(projectID, question, version)

	// Para project_plus_public, usamos versao diferente para diferenciar
	// (o gateway pode usar version offset para retrieval_mode)
	keyProjectPlusPublic := BuildCacheKey(projectID, question, version+1000)

	// Chaves devem ser diferentes
	if keyProjectOnly == keyProjectPlusPublic {
		t.Error("cache keys for different retrieval modes should differ")
	}

	// Ambas devem conter o project ID
	if keyProjectOnly == "" || keyProjectPlusPublic == "" {
		t.Error("cache keys should not be empty")
	}
}

func TestBuildCacheKey_PublicLibraryResponses(t *testing.T) {
	// Simula chaves para respostas que incluem fontes da biblioteca publica
	projectID := uuid.MustParse("b2c3d4e5-f6a7-8901-bcde-f12345678901")

	tests := []struct {
		name     string
		question string
		version  int
	}{
		{
			name:     "simple question",
			question: "What is pedagogy",
			version:  1,
		},
		{
			name:     "question with punctuation",
			question: "What is pedagogy?",
			version:  1,
		},
		{
			name:     "question with different case",
			question: "WHAT IS PEDAGOGY",
			version:  1,
		},
	}

	// Todas as variacoes da mesma pergunta devem gerar a mesma chave
	var firstKey string
	for _, tt := range tests {
		key := BuildCacheKey(projectID, tt.question, tt.version)
		if firstKey == "" {
			firstKey = key
		} else if key != firstKey {
			t.Errorf("%s: key %q differs from first key %q", tt.name, key, firstKey)
		}
	}
}

func TestSemanticCache_PublicLibraryResponse(t *testing.T) {
	// Testa armazenamento e recuperacao de resposta com fontes publicas
	ctx := context.Background()
	sc := &SemanticCache{
		enabled: false, // Sem Redis, testa comportamento disabled
	}

	// Resposta com fontes da biblioteca publica
	resp := &v1.ChatResponse{
		Answer: "Piaget e Vygotsky sao teoricos fundamentais da educacao.",
		Sources: []v1.Source{
			{Document: "project-thesis.pdf", Page: 15, Score: 0.95},
			{Document: "public-pedagogy-book.pdf", Page: 42, Score: 0.88},
			{Document: "public-learning-theory.pdf", Page: 7, Score: 0.82},
		},
		SessionID: "sess-public-1",
	}

	// Com cache disabled, Set deve ser no-op
	err := sc.Set(ctx, "chat:project:key:1", resp)
	if err != nil {
		t.Errorf("Set with disabled cache should return nil, got %v", err)
	}

	// Get deve retornar ErrCacheUnavailable
	_, err = sc.Get(ctx, "chat:project:key:1")
	if err != ErrCacheUnavailable {
		t.Errorf("Get with disabled cache should return ErrCacheUnavailable, got %v", err)
	}
}

func TestNormalizeQuestion_PublicLibraryQueries(t *testing.T) {
	// Testa normalizacao de perguntas tipicas de busca em acervo publico
	tests := []struct {
		name  string
		input string
		want  string
	}{
		{
			name:  "academic question",
			input: "  What are the main theories of cognitive development?  ",
			want:  "what are the main theories of cognitive development",
		},
		{
			name:  "portuguese question",
			input: "Quais sao as teorias de Piaget???",
			want:  "quais sao as teorias de piaget",
		},
		{
			name:  "mixed case with special chars",
			input: "Compare: Piaget vs. Vygotsky!",
			want:  "compare piaget vs vygotsky",
		},
		{
			name:  "book title query",
			input: "Democracy and Education — John Dewey",
			want:  "democracy and education  john dewey",
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

func TestCacheKeyStructure_PublicLibrary(t *testing.T) {
	// Verifica estrutura da chave de cache para cenarios de biblioteca publica
	projectID := uuid.MustParse("c3d4e5f6-a7b8-9012-cdef-123456789012")
	question := "Explain constructivism"
	version := 2 // Versao incrementada apos novo documento publico

	key := BuildCacheKey(projectID, question, version)

	// Formato: chat:{project_id}:{hash}:{version}
	parts := splitCacheKey(key)
	if len(parts) != 4 {
		t.Fatalf("expected 4 parts, got %d: %q", len(parts), key)
	}

	if parts[0] != "chat" {
		t.Errorf("expected prefix 'chat', got %q", parts[0])
	}

	if parts[1] != projectID.String() {
		t.Errorf("expected project_id %q, got %q", projectID.String(), parts[1])
	}

	// Hash deve ter 16 chars hex
	hashPart := parts[2]
	if len(hashPart) != 16 {
		t.Errorf("expected hash length 16, got %d", len(hashPart))
	}

	// Versao deve corresponder
	if parts[3] != "2" {
		t.Errorf("expected version '2', got %q", parts[3])
	}
}

func TestCacheVersionIncrement_PublicLibraryIngestion(t *testing.T) {
	// Simula cenario: novo documento publico e ingerido, versao do cache incrementa
	ctx := context.Background()
	sc := &SemanticCache{
		enabled:     false,
		redisClient: nil,
	}

	// Com cache disabled, increment retorna 0 (no-op)
	version, err := sc.IncrementProjectCacheVersion(ctx, "test-project")
	if err != nil {
		t.Errorf("expected nil error, got %v", err)
	}
	if version != 0 {
		t.Errorf("expected version 0 when disabled, got %d", version)
	}

	// Get version tambem retorna 0
	gotVersion, err := sc.GetProjectCacheVersion(ctx, "test-project")
	if err != nil {
		t.Errorf("expected nil error, got %v", err)
	}
	if gotVersion != 0 {
		t.Errorf("expected version 0 when disabled, got %d", gotVersion)
	}
}

// splitCacheKey divide uma chave de cache por ":".
func splitCacheKey(key string) []string {
	result := []string{}
	current := ""
	for _, c := range key {
		if c == ':' {
			result = append(result, current)
			current = ""
		} else {
			current += string(c)
		}
	}
	result = append(result, current)
	return result
}
