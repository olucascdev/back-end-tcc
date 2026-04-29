# Feature 2.6 — Webhook de Status para BFF

**Data:** 2026-04-28  
**Status:** Implementado

## Contexto

O gateway Go possui fila de PDF com worker pool (Feature 2.5) que processa documentos de forma assíncrona. Workers atualizam status de jobs para `ready` ou `error` após processamento. O BFF precisa ser notificado quando o processamento de um documento termina para atualizar a UI do usuário sem polling.

## Decisões Técnicas

### HMAC-SHA256 para assinatura
- Payload é assinado com HMAC-SHA256 usando secret compartilhado.
- BFF pode validar autenticidade e integridade do webhook.
- Header `X-Webhook-Signature: sha256=<hex>` segue padrão comum de webhooks (GitHub, Stripe).

### Idempotência
- Header `X-Idempotency-Key` usa `document_id` como chave.
- BFF pode detectar e ignorar entregas duplicadas.
- Simples e determinístico — mesmo documento gera mesma chave.

### Retry local no worker
- Máximo 3 tentativas com backoff exponencial: 1s, 2s, 4s.
- Implementado como loop local no `processJob` — sem dependência de fila externa.
- Falha no webhook **não** falha o job (best-effort).
- Após esgotar retries, erro é logado mas não propagado.

### Webhook desabilitável
- Se `WEBHOOK_URL` não está definido, webhook é silenciosamente ignorado.
- Permite desenvolvimento local sem endpoint de webhook.
- `Service.IsEnabled()` verifica URL antes de qualquer operação.

## Implementação

### 1. Serviço de Webhook
**Arquivo:** `services/go-gateway/internal/application/webhook/service.go`

- `Service` struct com `webhookURL`, `secret`, `httpClient` (timeout 10s).
- `NewService(webhookURL, secret string)` — factory.
- `SendWebhook(payload *v1.DocumentStatusWebhook) error`:
  1. Serializa payload para JSON.
  2. Gera HMAC-SHA256 do body com secret.
  3. Cria POST request com headers: `Content-Type`, `X-Webhook-Signature`, `X-Idempotency-Key`.
  4. Envia com timeout de 10s.
  5. Retorna erro se status HTTP >= 400.
  6. Log estruturado de envio.

### 2. Integração no Worker
**Arquivo:** `services/go-gateway/internal/infrastructure/queue/worker.go`

- Campo `webhookService *webhook.Service` adicionado ao `WorkerPool`.
- Novo construtor `NewWorkerPoolWithWebhook()` — mantém `NewWorkerPool()` para compatibilidade.
- `sendWebhookWithRetry()` — método privado com retry loop (3 tentativas, backoff 1s/2s/4s).
- Webhook enviado após transições para `ready` e `error`.
- Falha no webhook não propaga — job completa normalmente.

### 3. Configuração
**Arquivo:** `services/go-gateway/internal/config/config.go`

- Novos campos: `WebhookURL string`, `WebhookSecret string`.
- Env vars: `WEBHOOK_URL` (default ""), `WEBHOOK_SECRET` (default "").

### 4. App
**Arquivo:** `services/go-gateway/internal/app/app.go`

- Cria `webhookService` a partir do config.
- Passa para `NewWorkerPoolWithWebhook`.
- Log de inicialização indica se webhook está habilitado ou não.

### 5. Testes
**Arquivo:** `services/go-gateway/internal/application/webhook/service_test.go`

| Teste | Descrição |
|-------|-----------|
| `TestService_SendWebhookSuccess` | Mock server recebe payload, valida headers e body |
| `TestService_SendWebhookInvalidStatus` | Server retorna 500, serviço retorna erro |
| `TestService_SendWebhookSignature` | Valida que assinatura HMAC-SHA256 está correta |
| `TestService_SendWebhookDisabled` | URL vazia retorna nil sem enviar |

## Testes Executados

```bash
cd services/go-gateway
go test ./internal/application/webhook/... -v
```

- `TestService_SendWebhookSuccess` — ✅
- `TestService_SendWebhookInvalidStatus` — ✅
- `TestService_SendWebhookSignature` — ✅
- `TestService_SendWebhookDisabled` — ✅

## Próximos Passos

1. **Dead Letter Queue** — Se webhook falhar após todos os retries, persistir em DLQ para retry posterior.
2. **Métricas** — Adicionar contadores Prometheus de webhooks enviados/falhos.
3. **Configuração dinâmica** — Permitir atualizar URL/secret sem restart (via config reload).
4. **BFF consumer** — Implementar endpoint no BFF para receber e validar webhooks.

## Variáveis de Ambiente

| Variável | Default | Descrição |
|----------|---------|-----------|
| `WEBHOOK_URL` | `""` | URL do endpoint BFF para receber webhooks |
| `WEBHOOK_SECRET` | `""` | Secret para assinatura HMAC-SHA256 |

## Payload Exemplo

```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "project_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "status": "ready",
  "timestamp": "2026-04-28T10:30:00Z",
  "error_message": null,
  "metadata": null
}
```

## Headers da Request

```
POST /webhooks/document-status
Content-Type: application/json
X-Webhook-Signature: sha256=<hmac-sha256-hex>
X-Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```
