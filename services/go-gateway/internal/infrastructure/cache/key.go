// Package cache implementa cache semantico com Redis para respostas de chat.
package cache

import (
	"crypto/sha256"
	"fmt"
	"regexp"
	"strings"

	"github.com/google/uuid"
)

// nonSemanticChars remove pontuacao nao semantica, mantendo alfanumericos e espacos.
var nonSemanticChars = regexp.MustCompile(`[^a-zA-Z0-9\s]`)

// NormalizeQuestion normaliza uma pergunta para geracao de chave de cache.
// Remove pontuacao nao semantica, converte para minusculas, colapsa espacos.
func NormalizeQuestion(q string) string {
	// Trim espacos nas extremidades
	q = strings.TrimSpace(q)
	// Converter para minusculas
	q = strings.ToLower(q)
	// Remover pontuacao nao semantica (manter alfanumericos e espacos)
	q = nonSemanticChars.ReplaceAllString(q, "")
	// Colapsar multiplos espacos em unico espaco
	q = regexp.MustCompile(`\s+`).ReplaceAllString(q, " ")
	return q
}

// BuildCacheKey constroi a chave de cache no formato:
// "chat:{project_id}:{question_hash}:{version}"
// question_hash = SHA256 da pergunta normalizada, truncado para 16 chars hex.
func BuildCacheKey(projectID uuid.UUID, question string, version int) string {
	normalized := NormalizeQuestion(question)
	hash := sha256.Sum256([]byte(normalized))
	hashHex := fmt.Sprintf("%x", hash)[:16]
	return fmt.Sprintf("chat:%s:%s:%d", projectID.String(), hashHex, version)
}
