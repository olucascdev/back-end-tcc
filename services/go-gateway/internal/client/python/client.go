// Package python contem o cliente HTTP para comunicacao com o agente Python.
package python

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	v1 "github.com/olucasdev/tcc/go-gateway/internal/contracts/v1"
)

// Erros sentinelas para classificacao de falhas upstream.
var (
	ErrValidation      = errors.New("validation error from Python agent")
	ErrServiceUnavailable = errors.New("Python agent service unavailable")
	ErrTimeout         = errors.New("request to Python agent timed out")
)

// Client encapsula comunicacao HTTP com o agente Python.
type Client struct {
	baseURL    string
	timeout    time.Duration
	httpClient *http.Client
}

// NewClient cria um novo cliente Python com URL base e timeout.
func NewClient(baseURL string, timeout time.Duration) *Client {
	return &Client{
		baseURL: baseURL,
		timeout: timeout,
		httpClient: &http.Client{
			Timeout: timeout,
		},
	}
}

// ProcessDocument envia requisicao de processamento de documento ao agente Python.
func (c *Client) ProcessDocument(ctx context.Context, req *v1.ProcessDocumentRequest) (*v1.ProcessDocumentResponse, error) {
	return doRequest[v1.ProcessDocumentRequest, v1.ProcessDocumentResponse](
		ctx, c, http.MethodPost, "/process-document", req, "process-document",
	)
}

// Chat envia mensagem de chat com contexto RAG ao agente Python.
func (c *Client) Chat(ctx context.Context, req *v1.ChatRequest) (*v1.ChatResponse, error) {
	return doRequest[v1.ChatRequest, v1.ChatResponse](
		ctx, c, http.MethodPost, "/chat", req, "chat",
	)
}

// Summarize solicita resumo estruturado de documento ao agente Python.
func (c *Client) Summarize(ctx context.Context, req *v1.SummarizeRequest) (*v1.SummarizeResponse, error) {
	return doRequest[v1.SummarizeRequest, v1.SummarizeResponse](
		ctx, c, http.MethodPost, "/summarize-document", req, "summarize",
	)
}

// Compare solicita comparacao tematica entre documentos ao agente Python.
func (c *Client) Compare(ctx context.Context, req *v1.CompareRequest) (*v1.CompareResponse, error) {
	return doRequest[v1.CompareRequest, v1.CompareResponse](
		ctx, c, http.MethodPost, "/compare-documents", req, "compare",
	)
}

// doRequest executa chamada HTTP generica com tratamento de erro padronizado.
// Serializa req como JSON, envia para endpoint relativo, desserializa resposta.
// Classifica erros por tipo HTTP para mapeamento correto no handler.
func doRequest[Req any, Resp any](
	ctx context.Context,
	c *Client,
	method, endpoint string,
	req *Req,
	opName string,
) (*Resp, error) {
	// Serializar payload
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal %s request: %w", opName, err)
	}

	// Construir URL completa
	url := c.baseURL + endpoint

	// Criar request HTTP com contexto
	httpReq, err := http.NewRequestWithContext(ctx, method, url, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("failed to create %s request: %w", opName, err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	// Extrair request_id do contexto para logging (se disponivel)
	if requestID, ok := ctx.Value("request_id").(string); ok && requestID != "" {
		httpReq.Header.Set("X-Request-ID", requestID)
	}

	// Log da requisicao
	slog.Info("python agent request",
		slog.String("operation", opName),
		slog.String("method", method),
		slog.String("url", url),
	)

	// Executar chamada HTTP
	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		// Classificar erro de conexao/timeout
		if ctx.Err() == context.DeadlineExceeded || errors.Is(err, context.DeadlineExceeded) {
			slog.Warn("python agent request timeout",
				slog.String("operation", opName),
				slog.String("url", url),
			)
			return nil, ErrTimeout
		}
		// Timeout do http.Client tambem gera erro com "Client.Timeout exceeded"
		if strings.Contains(err.Error(), "Client.Timeout exceeded") {
			slog.Warn("python agent request timeout (client timeout)",
				slog.String("operation", opName),
				slog.String("url", url),
			)
			return nil, ErrTimeout
		}
		slog.Error("python agent connection error",
			slog.String("operation", opName),
			slog.String("url", url),
			slog.String("error", err.Error()),
		)
		return nil, ErrServiceUnavailable
	}
	defer resp.Body.Close()

	// Ler corpo da resposta para logging e parsing
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read %s response body: %w", opName, err)
	}

	// Log da resposta (status e tamanho)
	slog.Info("python agent response",
		slog.String("operation", opName),
		slog.Int("status", resp.StatusCode),
		slog.Int("body_size", len(respBody)),
	)

	// Classificar erro por status HTTP
	switch {
	case resp.StatusCode >= 400 && resp.StatusCode < 500:
		// 4xx -> erro de validacao do lado Python
		slog.Warn("python agent validation error",
			slog.String("operation", opName),
			slog.Int("status", resp.StatusCode),
			slog.String("body", string(respBody)),
		)
		return nil, fmt.Errorf("%w: %s", ErrValidation, string(respBody))
	case resp.StatusCode >= 500:
		// 5xx -> erro interno do Python
		slog.Error("python agent server error",
			slog.String("operation", opName),
			slog.Int("status", resp.StatusCode),
			slog.String("body", string(respBody)),
		)
		return nil, ErrServiceUnavailable
	}

	// Desserializar resposta JSON
	var result Resp
	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("failed to unmarshal %s response: %w", opName, err)
	}

	return &result, nil
}

// BaseURL retorna a URL base do cliente (util para testes).
func (c *Client) BaseURL() string {
	return c.baseURL
}

// Timeout retorna o timeout configurado (util para testes).
func (c *Client) Timeout() time.Duration {
	return c.timeout
}
