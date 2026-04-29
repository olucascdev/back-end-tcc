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
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/circuitbreaker"
	"github.com/olucasdev/tcc/go-gateway/internal/infrastructure/retry"
)

// Erros sentinelas para classificacao de falhas upstream.
var (
	ErrValidation         = errors.New("validation error from Python agent")
	ErrServiceUnavailable = errors.New("Python agent service unavailable")
	ErrTimeout            = errors.New("request to Python agent timed out")
)

// defaultTimeout usado quando operacao nao possui timeout especifico no mapa.
const defaultTimeout = 30 * time.Second

// Client encapsula comunicacao HTTP com o agente Python.
type Client struct {
	baseURL     string
	timeouts    map[string]time.Duration
	httpClient  *http.Client
	breakers    *circuitbreaker.BreakerGroup
	retryPolicy *retry.Policy
}

// NewClient cria um novo cliente Python com URL base, mapa de timeouts por operacao
// e grupo de circuit breakers. Se breakers for nil, o client opera sem circuit breaker.
// Operacoes conhecidas: "chat", "summarize", "compare", "process-document", "health".
// Se uma operacao nao estiver no mapa, usa default de 30s.
// Wrapper para backward compat — delega para NewClientWithResilience sem retry.
func NewClient(baseURL string, timeouts map[string]time.Duration, breakers *circuitbreaker.BreakerGroup) *Client {
	return NewClientWithResilience(baseURL, timeouts, breakers, nil)
}

// NewClientWithResilience cria um novo cliente Python com todos os mecanismos
// de resiliencia: timeouts por operacao, circuit breakers e politica de retry.
// Se retryPolicy for nil, o retry nao e aplicado (comportamento legacy).
func NewClientWithResilience(baseURL string, timeouts map[string]time.Duration, breakers *circuitbreaker.BreakerGroup, retryPolicy *retry.Policy) *Client {
	return &Client{
		baseURL:  baseURL,
		timeouts: timeouts,
		httpClient: &http.Client{
			// Timeout do httpClient e deixado alto; o controle real
			// e feito via context.WithTimeout por operacao.
			Timeout: 5 * time.Minute,
		},
		breakers:    breakers,
		retryPolicy: retryPolicy,
	}
}

// getTimeout retorna o timeout configurado para uma operacao.
// Se nao encontrado no mapa, retorna defaultTimeout (30s).
func (c *Client) getTimeout(opName string) time.Duration {
	if t, ok := c.timeouts[opName]; ok {
		return t
	}
	return defaultTimeout
}

// ProcessDocument envia requisicao de processamento de documento ao agente Python.
// A chamada e protegida por circuit breaker para evitar falhas em cascata.
func (c *Client) ProcessDocument(ctx context.Context, req *v1.ProcessDocumentRequest) (*v1.ProcessDocumentResponse, error) {
	if c.breakers == nil {
		return doRequest[v1.ProcessDocumentRequest, v1.ProcessDocumentResponse](
			ctx, c, http.MethodPost, "/process-document", req, "process-document",
		)
	}
	result, err := c.breakers.Execute("process-document", func() (interface{}, error) {
		return doRequest[v1.ProcessDocumentRequest, v1.ProcessDocumentResponse](
			ctx, c, http.MethodPost, "/process-document", req, "process-document",
		)
	})
	if err != nil {
		return nil, err
	}
	return result.(*v1.ProcessDocumentResponse), nil
}

// Chat envia mensagem de chat com contexto RAG ao agente Python.
// A chamada e protegida por circuit breaker para evitar falhas em cascata.
// Se retryPolicy estiver configurada, erros retryable (timeout, unavailable)
// sao retentados com backoff exponencial.
func (c *Client) Chat(ctx context.Context, req *v1.ChatRequest) (*v1.ChatResponse, error) {
	fn := func() (interface{}, error) {
		return doRequest[v1.ChatRequest, v1.ChatResponse](
			ctx, c, http.MethodPost, "/chat", req, "chat",
		)
	}

	if c.breakers == nil && c.retryPolicy == nil {
		res, err := fn()
		if err != nil {
			return nil, err
		}
		return res.(*v1.ChatResponse), nil
	}

	if c.breakers == nil {
		// Sem breaker, mas com retry
		var result *v1.ChatResponse
		err := c.retryPolicy.Execute(ctx, "chat", func() error {
			res, err := fn()
			if err != nil {
				return err
			}
			result = res.(*v1.ChatResponse)
			return nil
		})
		return result, err
	}

	if c.retryPolicy == nil {
		// Com breaker, sem retry (comportamento atual)
		result, err := c.breakers.Execute("chat", fn)
		if err != nil {
			return nil, err
		}
		return result.(*v1.ChatResponse), nil
	}

	// Com breaker e retry: retry envolve o breaker
	var result *v1.ChatResponse
	err := c.retryPolicy.Execute(ctx, "chat", func() error {
		res, err := c.breakers.Execute("chat", fn)
		if err != nil {
			return err
		}
		result = res.(*v1.ChatResponse)
		return nil
	})
	return result, err
}

// Summarize solicita resumo estruturado de documento ao agente Python.
// A chamada e protegida por circuit breaker para evitar falhas em cascata.
// Se retryPolicy estiver configurada, erros retryable sao retentados.
func (c *Client) Summarize(ctx context.Context, req *v1.SummarizeRequest) (*v1.SummarizeResponse, error) {
	fn := func() (interface{}, error) {
		return doRequest[v1.SummarizeRequest, v1.SummarizeResponse](
			ctx, c, http.MethodPost, "/summarize-document", req, "summarize",
		)
	}

	if c.breakers == nil && c.retryPolicy == nil {
		res, err := fn()
		if err != nil {
			return nil, err
		}
		return res.(*v1.SummarizeResponse), nil
	}

	if c.breakers == nil {
		var result *v1.SummarizeResponse
		err := c.retryPolicy.Execute(ctx, "summarize", func() error {
			res, err := fn()
			if err != nil {
				return err
			}
			result = res.(*v1.SummarizeResponse)
			return nil
		})
		return result, err
	}

	if c.retryPolicy == nil {
		result, err := c.breakers.Execute("summarize", fn)
		if err != nil {
			return nil, err
		}
		return result.(*v1.SummarizeResponse), nil
	}

	var result *v1.SummarizeResponse
	err := c.retryPolicy.Execute(ctx, "summarize", func() error {
		res, err := c.breakers.Execute("summarize", fn)
		if err != nil {
			return err
		}
		result = res.(*v1.SummarizeResponse)
		return nil
	})
	return result, err
}

// Compare solicita comparacao tematica entre documentos ao agente Python.
// A chamada e protegida por circuit breaker para evitar falhas em cascata.
// Se retryPolicy estiver configurada, erros retryable sao retentados.
func (c *Client) Compare(ctx context.Context, req *v1.CompareRequest) (*v1.CompareResponse, error) {
	fn := func() (interface{}, error) {
		return doRequest[v1.CompareRequest, v1.CompareResponse](
			ctx, c, http.MethodPost, "/compare-documents", req, "compare",
		)
	}

	if c.breakers == nil && c.retryPolicy == nil {
		res, err := fn()
		if err != nil {
			return nil, err
		}
		return res.(*v1.CompareResponse), nil
	}

	if c.breakers == nil {
		var result *v1.CompareResponse
		err := c.retryPolicy.Execute(ctx, "compare", func() error {
			res, err := fn()
			if err != nil {
				return err
			}
			result = res.(*v1.CompareResponse)
			return nil
		})
		return result, err
	}

	if c.retryPolicy == nil {
		result, err := c.breakers.Execute("compare", fn)
		if err != nil {
			return nil, err
		}
		return result.(*v1.CompareResponse), nil
	}

	var result *v1.CompareResponse
	err := c.retryPolicy.Execute(ctx, "compare", func() error {
		res, err := c.breakers.Execute("compare", fn)
		if err != nil {
			return err
		}
		result = res.(*v1.CompareResponse)
		return nil
	})
	return result, err
}

// ResearchGaps solicita identificacao de lacunas de pesquisa ao agente Python.
// A chamada e protegida por circuit breaker para evitar falhas em cascata.
// Se retryPolicy estiver configurada, erros retryable sao retentados.
func (c *Client) ResearchGaps(ctx context.Context, req *v1.ResearchGapRequest) (*v1.ResearchGapResponse, error) {
	fn := func() (interface{}, error) {
		return doRequest[v1.ResearchGapRequest, v1.ResearchGapResponse](
			ctx, c, http.MethodPost, "/research/gaps", req, "research-gaps",
		)
	}

	if c.breakers == nil && c.retryPolicy == nil {
		res, err := fn()
		if err != nil {
			return nil, err
		}
		return res.(*v1.ResearchGapResponse), nil
	}

	if c.breakers == nil {
		var result *v1.ResearchGapResponse
		err := c.retryPolicy.Execute(ctx, "research-gaps", func() error {
			res, err := fn()
			if err != nil {
				return err
			}
			result = res.(*v1.ResearchGapResponse)
			return nil
		})
		return result, err
	}

	if c.retryPolicy == nil {
		result, err := c.breakers.Execute("research-gaps", fn)
		if err != nil {
			return nil, err
		}
		return result.(*v1.ResearchGapResponse), nil
	}

	var result *v1.ResearchGapResponse
	err := c.retryPolicy.Execute(ctx, "research-gaps", func() error {
		res, err := c.breakers.Execute("research-gaps", fn)
		if err != nil {
			return err
		}
		result = res.(*v1.ResearchGapResponse)
		return nil
	})
	return result, err
}

// doRequest executa chamada HTTP generica com tratamento de erro padronizado.
// Cria contexto com deadline baseado no timeout da operacao.
// Serializa req como JSON, envia para endpoint relativo, desserializa resposta.
// Classifica erros por tipo HTTP para mapeamento correto no handler.
// Loga request completo (method, url, duration, status) em JSON.
func doRequest[Req any, Resp any](
	ctx context.Context,
	c *Client,
	method, endpoint string,
	req *Req,
	opName string,
) (*Resp, error) {
	// Garantir contexto valido mesmo quando chamado com nil (ex: testes)
	if ctx == nil {
		ctx = context.Background()
	}

	// Criar contexto com timeout especifico da operacao
	timeout := c.getTimeout(opName)
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	// Serializar payload
	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal %s request: %w", opName, err)
	}

	// Construir URL completa
	url := c.baseURL + endpoint

	// Criar request HTTP com contexto (contem deadline do timeout)
	httpReq, err := http.NewRequestWithContext(ctx, method, url, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("failed to create %s request: %w", opName, err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	// Extrair request_id do contexto para propagacao ao Python
	// O middleware RequestID injeta o valor no contexto Go
	if requestID := getRequestIDFromContext(ctx); requestID != "" {
		httpReq.Header.Set("X-Request-ID", requestID)
	}

	// Log da requisicao
	slog.Info("python agent request",
		slog.String("operation", opName),
		slog.String("method", method),
		slog.String("url", url),
		slog.String("request_id", getRequestIDFromContext(ctx)),
		slog.Duration("timeout", timeout),
	)

	// Executar chamada HTTP com medicao de duracao
	start := time.Now()
	resp, err := c.httpClient.Do(httpReq)
	duration := time.Since(start)

	if err != nil {
		// Classificar erro de conexao/timeout
		if ctx.Err() == context.DeadlineExceeded || errors.Is(err, context.DeadlineExceeded) {
			slog.Warn("python agent request timeout",
				slog.String("operation", opName),
				slog.String("url", url),
				slog.String("request_id", getRequestIDFromContext(ctx)),
				slog.Duration("duration", duration),
				slog.Duration("timeout", timeout),
			)
			return nil, ErrTimeout
		}
		// Timeout do http.Client tambem gera erro com "Client.Timeout exceeded"
		if strings.Contains(err.Error(), "Client.Timeout exceeded") {
			slog.Warn("python agent request timeout (client timeout)",
				slog.String("operation", opName),
				slog.String("url", url),
				slog.String("request_id", getRequestIDFromContext(ctx)),
				slog.Duration("duration", duration),
				slog.Duration("timeout", timeout),
			)
			return nil, ErrTimeout
		}
		slog.Error("python agent connection error",
			slog.String("operation", opName),
			slog.String("url", url),
			slog.String("error", err.Error()),
			slog.String("request_id", getRequestIDFromContext(ctx)),
			slog.Duration("duration", duration),
		)
		return nil, ErrServiceUnavailable
	}
	defer resp.Body.Close()

	// Ler corpo da resposta para logging e parsing
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read %s response body: %w", opName, err)
	}

	// Log da resposta com duracao e status
	slog.Info("python agent response",
		slog.String("operation", opName),
		slog.Int("status", resp.StatusCode),
		slog.Int("body_size", len(respBody)),
		slog.String("request_id", getRequestIDFromContext(ctx)),
		slog.Duration("duration", duration),
	)

	// Classificar erro por status HTTP
	switch {
	case resp.StatusCode >= 400 && resp.StatusCode < 500:
		// 4xx -> erro de validacao do lado Python
		slog.Warn("python agent validation error",
			slog.String("operation", opName),
			slog.Int("status", resp.StatusCode),
			slog.String("body", string(respBody)),
			slog.String("request_id", getRequestIDFromContext(ctx)),
			slog.Duration("duration", duration),
		)
		return nil, fmt.Errorf("%w: %s", ErrValidation, string(respBody))
	case resp.StatusCode >= 500:
		// 5xx -> erro interno do Python
		slog.Error("python agent server error",
			slog.String("operation", opName),
			slog.Int("status", resp.StatusCode),
			slog.String("body", string(respBody)),
			slog.String("request_id", getRequestIDFromContext(ctx)),
			slog.Duration("duration", duration),
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

// getRequestIDFromContext extrai request_id do contexto Go.
func getRequestIDFromContext(ctx context.Context) string {
	if id, ok := ctx.Value("request_id").(string); ok {
		return id
	}
	return ""
}

// BaseURL retorna a URL base do cliente (util para testes).
func (c *Client) BaseURL() string {
	return c.baseURL
}

// GetTimeout retorna o timeout configurado para uma operacao (util para testes).
func (c *Client) GetTimeout(opName string) time.Duration {
	return c.getTimeout(opName)
}
