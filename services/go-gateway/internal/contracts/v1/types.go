// Package v1 contem os contratos internos versao 1 compartilhados
// entre o gateway Go e o agente Python.
//
// Cada struct possui tags json para serializacao compativel com os
// schemas Pydantic do lado Python.
package v1

import (
	"time"

	"github.com/google/uuid"
)

// Source representa uma citacao de documento usada como fonte
// em respostas de chat ou comparacao.
type Source struct {
	Document string  `json:"document"`
	Page     int     `json:"page"`
	Section  *string `json:"section,omitempty"`
	Score    float64 `json:"score"`
}

// ---------------------------------------------------------------------------
// ProcessDocument – processamento assincrono de documento
// ---------------------------------------------------------------------------

// ProcessDocumentRequest requisicao para processar um documento recem-ingestado.
type ProcessDocumentRequest struct {
	ProjectID  uuid.UUID              `json:"project_id"`
	DocumentID uuid.UUID              `json:"document_id"`
	StorageKey string                 `json:"storage_key"`
	SourceType string                 `json:"source_type"`
	Metadata   map[string]interface{} `json:"metadata,omitempty"`
}

// ProcessDocumentResponse resposta do agente apos aceitar/rejeitar o processamento.
type ProcessDocumentResponse struct {
	DocumentID   uuid.UUID  `json:"document_id"`
	Status       string     `json:"status"` // pending | processing | ready | error
	ChunksCount  *int       `json:"chunks_count,omitempty"`
	ProcessedAt  *time.Time `json:"processed_at,omitempty"`
	ErrorMessage *string    `json:"error_message,omitempty"`
}

// ---------------------------------------------------------------------------
// Chat – interacao RAG com fontes
// ---------------------------------------------------------------------------

// ChatRequest requisicao de chat com contexto RAG.
type ChatRequest struct {
	ProjectID uuid.UUID              `json:"project_id"`
	SessionID string                 `json:"session_id"`
	Message   string                 `json:"message"`
	Filters   map[string]interface{} `json:"filters,omitempty"`
}

// ChatResponse resposta do chat com citacoes.
type ChatResponse struct {
	Answer    string   `json:"answer"`
	Sources   []Source `json:"sources"`
	SessionID string   `json:"session_id"`
	CreatedAt time.Time `json:"created_at"`
}

// ---------------------------------------------------------------------------
// Summarize – resumo estruturado de documento
// ---------------------------------------------------------------------------

// SummarizeRequest requisicao de resumo de documento.
type SummarizeRequest struct {
	DocumentID uuid.UUID `json:"document_id"`
	ProjectID  uuid.UUID `json:"project_id"`
	Format     string    `json:"format"`
}

// SummarizeResponse resumo estruturado gerado pelo agente.
type SummarizeResponse struct {
	DocumentID uuid.UUID         `json:"document_id"`
	Summary    map[string]string `json:"summary"` // objective, methodology, results, conclusion
	CreatedAt  time.Time         `json:"created_at"`
}

// ---------------------------------------------------------------------------
// Compare – comparacao tematica entre documentos
// ---------------------------------------------------------------------------

// CompareRequest requisicao de comparacao entre dois ou mais documentos.
type CompareRequest struct {
	ProjectID   uuid.UUID   `json:"project_id"`
	DocumentIDs []uuid.UUID `json:"document_ids"`
	Theme       string      `json:"theme"`
}

// CompareResponse resultado da comparacao tematica.
type CompareResponse struct {
	ProjectID  uuid.UUID         `json:"project_id"`
	Comparison map[string]string `json:"comparison"`
	Sources    []Source          `json:"sources"`
	CreatedAt  time.Time         `json:"created_at"`
}

// ---------------------------------------------------------------------------
// Webhook – notificacao de status de documento
// ---------------------------------------------------------------------------

// DocumentStatusWebhook payload enviado ao gateway quando o status de
// um documento muda.
type DocumentStatusWebhook struct {
	DocumentID   uuid.UUID              `json:"document_id"`
	ProjectID    uuid.UUID              `json:"project_id"`
	Status       string                 `json:"status"`
	Timestamp    time.Time              `json:"timestamp"`
	ErrorMessage *string                `json:"error_message,omitempty"`
	Metadata     map[string]interface{} `json:"metadata,omitempty"`
}
