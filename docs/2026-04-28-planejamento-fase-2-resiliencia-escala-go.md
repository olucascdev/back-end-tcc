# Planejamento Fase 2 - Resiliencia e escala no Go Gateway

## Contexto
A Fase 1 concluiu MVP RAG funcional ponta-a-ponta com integracao real Go -> Python, chat com fontes, persistencia de sessao e observabilidade minima. O proximo passo e endurecer o gateway Go para operacao sob carga e falha parcial de dependencias.

Escopo desta fase:
- resiliencia de chamadas Go -> Python
- controle de consumo por usuario/projeto
- processamento assincrono de documentos
- notificacao de status para BFF
- telemetria operacional para componentes de resiliencia

## Decisoes tecnicas
- Fase 2 fica restrita ao dominio de resiliencia e escala do gateway Go.
- Retry sera aplicado apenas em operacoes idempotentes.
- `process-document` nao tera retry cego sem garantia de idempotencia.
- Circuit breaker sera aplicado por operacao de upstream, com estados `closed`, `open`, `half-open`.
- Rate limiting usara token bucket por chave de consumo (`user_id` + `project_id`).
- Fila PDF usara workers concorrentes com canais para desacoplar ingestao de documento do caminho sincrono de chat.
- Webhook de status de documento tera assinatura HMAC e cabecalho de idempotencia.

## Implementacao

### Feature 2.1 - Timeout por operacao + politica de idempotencia
Escopo:
- separar timeout por endpoint upstream (`chat`, `summarize`, `compare`, `process-document`, `health`)
- definir matriz de idempotencia por operacao em documento tecnico
- bloquear retry para operacoes nao idempotentes por padrao

Criterios de aceite:
- timeout configuravel por operacao via ambiente
- handlers usam timeout correto conforme tipo da operacao

### Feature 2.2 - Circuit breaker Go -> Python
Escopo:
- adicionar breaker por operacao upstream
- configurar limiar de falha, janela de observacao e cooldown
- responder erro elegante sem chamada remota quando circuito aberto

Criterios de aceite:
- transicoes `closed -> open -> half-open -> closed` observaveis
- indisponibilidade Python nao derruba fluxo HTTP do gateway

### Feature 2.3 - Retry com backoff exponencial (idempotentes)
Escopo:
- aplicar retry com jitter apenas em `chat`, `summarize`, `compare`
- nao aplicar retry automatico em `process-document`
- instrumentar contador de tentativas e falhas finais

Criterios de aceite:
- retries respeitam limite maximo e timeout total da operacao
- erro final preserva classificacao (`timeout`, `unavailable`, `validation`)

### Feature 2.4 - Rate limiting por usuario/projeto
Escopo:
- middleware de token bucket por `user_id` e `project_id`
- fallback por IP quando identificadores nao estiverem presentes
- resposta `429` com payload padronizado

Criterios de aceite:
- requisicoes acima do limite retornam `429`
- requisicoes dentro do limite seguem sem degradacao relevante

### Feature 2.5 - Fila concorrente de processamento de PDF
Escopo:
- enfileirar jobs de `process-document`
- executar processamento com pool de workers
- persistir estado de job (`pending`, `processing`, `ready`, `error`)

Criterios de aceite:
- upload retorna aceite rapido sem bloquear por processamento longo
- chat segue responsivo durante picos de ingestao

### Feature 2.6 - Webhook de status para BFF
Escopo:
- enviar webhook em transicoes finais (`ready`, `error`)
- incluir `document_id`, `project_id`, `status`, `timestamp` e metadados minimos
- assinar payload com HMAC e enviar idempotency key

Criterios de aceite:
- BFF recebe notificacao consistente por documento
- reentrega nao gera efeito colateral destrutivo

### Artefatos esperados
- `services/go-gateway/internal/client/python/*`
- `services/go-gateway/internal/middleware/*`
- `services/go-gateway/internal/application/*`
- `services/go-gateway/internal/infrastructure/*`
- `services/go-gateway/internal/contracts/v1/*`
- `services/go-gateway/internal/api/v1/handlers/*`
- `services/go-gateway/internal/config/*`
- `docs/*feature-2-*.md`

## Testes executados
Este documento representa planejamento e definicao de escopo da Fase 2.

Testes obrigatorios durante execucao:
- unitarios: rate limiter, breaker state machine, retry policy, queue workers
- integracao: handlers proxy com cenarios de timeout, 5xx, breaker aberto, retry
- carga: latencia p95/p99 e throughput com chat concorrente + ingestao PDF
- contrato: payload e assinatura de webhook

## Proximos passos
1. Converter este planejamento em checklist operacional no OpenSpec (`tasks.md`) com granularidade de 1-2 dias por item.
2. Implementar na ordem: timeout/idempotencia -> circuit breaker -> retry -> rate limiting -> fila -> webhook.
3. Criar um arquivo em `docs/` para cada feature concluida na Fase 2 com evidencias de teste.
