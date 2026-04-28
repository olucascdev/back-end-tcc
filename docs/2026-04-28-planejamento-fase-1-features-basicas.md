# Planejamento Fase 1 - Features basicas (MVP RAG)

## Contexto
A Fase 0 entregou fundacao tecnica: estrutura de servicos, migracoes, contratos v1, stubs de API e quality gates iniciais. A Fase 1 foca MVP funcional de RAG por projeto, com fluxo real de processamento de documento e chat com fontes.

Objetivo principal:
- sair de stubs para fluxo real ponta-a-ponta via Go gateway e Python agent.

Escopo da fase:
- `POST /process-document` real
- `POST /chat` real com fontes rastreaveis
- integracao real Go -> Python
- persistencia de sessao e historico essencial
- observabilidade minima para operacao do MVP

## Decisoes tecnicas
- Implementar por vertical slice para reduzir risco:
  1. ingestao/embeddings
  2. proxy Go real
  3. chat RAG
  4. memoria/sessao
  5. observabilidade final
- Filtro por `project_id` obrigatorio na busca vetorial para evitar contaminacao de contexto.
- Resposta do chat deve sempre incluir `sources[]` quando houver contexto relevante.
- Em contexto insuficiente, responder limitacao explicitamente (sem alucinacao).
- Manter contratos v1; breaking change apenas com nova versao.

## Implementacao (features basicas)

### Feature 1.1 - Processamento real de documento (Python)
Escopo:
- Implementar pipeline real em `POST /process-document`:
  - obter arquivo em MinIO/S3
  - extrair texto
  - chunking
  - gerar embeddings
  - persistir em NeonDB/pgvector

Dados minimos por chunk:
- `project_id`
- `document_id`
- `filename`
- `page`
- `source_type`

Aceite:
- documento valido gera chunks e grava embeddings
- erro estruturado para documento invalido/inacessivel

### Feature 1.2 - Integracao real Go -> Python (process-document e chat)
Escopo:
- remover mock de handlers Go para `documents/process` e `chat`
- usar client HTTP real com timeout e retry basico
- padronizar erro de upstream

Aceite:
- Go encaminha chamadas reais ao Python
- falha no Python retorna erro elegante no Go

### Feature 1.3 - Chat RAG real com fontes (Python)
Escopo:
- implementar `POST /chat` real:
  - embedding da pergunta
  - similarity search no pgvector (filtro `project_id`)
  - composicao de contexto
  - chamada LLM
  - retorno com `answer` e `sources`

Aceite:
- resposta com fonte rastreavel (`document`, `page`, `section?`, `score`)
- sem contexto suficiente, resposta explicita limitacao

### Feature 1.4 - Persistencia de sessao e historico
Escopo:
- persistir memoria de sessao em `agent_sessions`
- persistir interacoes essenciais em `conversations`
- reutilizar contexto por `session_id`

Aceite:
- mensagens sequenciais na mesma sessao preservam contexto

### Feature 1.5 - Observabilidade minima do MVP
Escopo:
- propagar `request_id` Go -> Python
- logs estruturados nos endpoints core
- metricas basicas de latencia, erro e throughput

Aceite:
- troubleshooting fim-a-fim possivel por `request_id`
- endpoint `/metrics` funcional em ambos servicos

## Ordem de execucao recomendada
1. Feature 1.1
2. Feature 1.2 (process-document)
3. Feature 1.3
4. Feature 1.2 (chat)
5. Feature 1.4
6. Feature 1.5

## Testes executados
Este documento representa planejamento. Nenhum teste funcional novo executado nesta etapa.

Testes obrigatorios durante execucao da fase:
- unitarios de parser/chunker/mapper
- integracao API Python (`process-document`, `chat`)
- integracao Go client (sucesso, timeout, erro upstream)
- smoke E2E: Go -> Python -> NeonDB/pgvector

## Proximos passos
1. Converter este planejamento em checklist operacional no `tasks.md` da change ativa.
2. Iniciar implementacao pela Feature 1.1 (pipeline de documento real).
3. Criar um arquivo em `docs/` para cada feature entregue durante a Fase 1.
