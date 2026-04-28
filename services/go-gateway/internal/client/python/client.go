// Package python contem o cliente HTTP para comunicacao com o agente Python.
// Por enquanto retorna mocks; chamadas reais serao implementadas posteriormente.
package python

import (
	"context"
	"time"

	"github.com/google/uuid"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
)

// Client encapsula comunicacao HTTP com o agente Python.
type Client struct {
	baseURL string
	timeout time.Duration
}

// NewClient cria um novo cliente Python com URL base e timeout.
func NewClient(baseURL string, timeout time.Duration) *Client {
	return &Client{
		baseURL: baseURL,
		timeout: timeout,
	}
}

// ProcessDocument envia requisicao de processamento de documento.
// Stub: retorna mock sem chamada HTTP real.
func (c *Client) ProcessDocument(ctx context.Context, req *v1.ProcessDocumentRequest) *v1.ProcessDocumentResponse {
	// TODO: implementar chamada HTTP real para Python /process-document
	chunks := 0
	status := "pending"
	return &v1.ProcessDocumentResponse{
		DocumentID:  req.DocumentID,
		Status:      status,
		ChunksCount: &chunks,
	}
}

// Chat envia mensagem de chat com contexto RAG.
// Stub: retorna mock sem chamada HTTP real.
func (c *Client) Chat(ctx context.Context, req *v1.ChatRequest) *v1.ChatResponse {
	// TODO: implementar chamada HTTP real para Python /chat
	return &v1.ChatResponse{
		Answer:    "Resposta mock do agente Python.",
		Sources:   []v1.Source{},
		SessionID: req.SessionID,
		CreatedAt: time.Now().UTC(),
	}
}

// Summarize solicita resumo estruturado de documento.
// Stub: retorna mock sem chamada HTTP real.
func (c *Client) Summarize(ctx context.Context, req *v1.SummarizeRequest) *v1.SummarizeResponse {
	// TODO: implementar chamada HTTP real para Python /summarize-document
	return &v1.SummarizeResponse{
		DocumentID: req.DocumentID,
		Summary: map[string]string{
			"objective":   "Mock objective",
			"methodology": "Mock methodology",
			"results":     "Mock results",
			"conclusion":  "Mock conclusion",
		},
		CreatedAt: time.Now().UTC(),
	}
}

// Compare solicita comparacao tematica entre documentos.
// Stub: retorna mock sem chamada HTTP real.
func (c *Client) Compare(ctx context.Context, req *v1.CompareRequest) *v1.CompareResponse {
	// TODO: implementar chamada HTTP real para Python /compare-documents
	return &v1.CompareResponse{
		ProjectID: req.ProjectID,
		Comparison: map[string]string{
			"theme": "Mock comparison for theme: " + req.Theme,
		},
		Sources:   []v1.Source{},
		CreatedAt: time.Now().UTC(),
	}
}

// BaseURL retorna a URL base do cliente (util para testes).
func (c *Client) BaseURL() string {
	return c.baseURL
}

// Timeout retorna o timeout configurado (util para testes).
func (c *Client) Timeout() time.Duration {
	return c.timeout
}
