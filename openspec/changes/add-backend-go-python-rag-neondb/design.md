## Contexto
Arquitetura backend separada em serviços especializados:
- Go/Gin para orquestração e resiliência de chamadas de IA.
- Python/FastAPI+Agno para pipeline RAG e operações semânticas.
- NeonDB serverless (PostgreSQL + pgvector) para dados relacionais e vetoriais.
- MongoDB para catálogo público de livros indexáveis.
- Redis para rate limiting e cache semântico.

## Objetivos
- Garantir especificação clara de responsabilidades por serviço.
- Formalizar requisitos não funcionais de resiliência, performance e rastreabilidade.
- Permitir implementação incremental por features com critérios de aceite testáveis.
- Sustentar avaliação acadêmica de qualidade RAG e desempenho arquitetural.

## Não Objetivos
- Implementar frontend ou BFF neste change.
- Definir provedor único de LLM (deve ser configurável).
- Fechar benchmark definitivo antes do MVP funcional.

## Decisões
- Go/Gin como gateway de IA:
  - Motivo: concorrência eficiente com goroutines/channels, baixa latência e bom controle de timeout/retry/circuit breaker.
- FastAPI+Agno como agente RAG:
  - Motivo: ecossistema maduro para NLP/RAG e integração prática com vector stores.
- NeonDB serverless como banco principal:
  - Motivo: simplificação operacional, custo elástico, unificação de dados transacionais e embeddings.
- MongoDB dedicado ao catálogo público:
  - Motivo: esquema flexível para metadados heterogêneos de fontes públicas.
- Redis para cache semântico e controle de consumo:
  - Motivo: resposta rápida em leituras frequentes e suporte à limitação por usuário.

## Arquitetura lógica
1. BFF envia requisições de chat/processamento ao Go.
2. Go aplica rate limit, consulta cache semântico e decide chamada ao Python.
3. Python executa RAG e persiste sessão/contexto no NeonDB.
4. Para PDFs, Go gerencia fila concorrente e notifica BFF por webhook ao concluir.
5. Indexador público atualiza MongoDB (metadados) e NeonDB/pgvector (embeddings públicos).

## Dados e persistência
- NeonDB:
  - `users`, `projects`, `documents`, `conversations`, `agent_sessions`, `embeddings`.
  - Índices vetoriais para similaridade por projeto e por acervo público.
- MongoDB:
  - `books` com `title`, `authors`, `isbn`, `gutenberg_id`, `ol_key`, `formats`, `indexed`, `indexed_at`.

## Segurança e resiliência
- Timeouts e retries com backoff entre Go e Python.
- Circuit breaker no Go para degradar com erro elegante quando Python indisponível.
- Idempotência para jobs de processamento e indexação.
- Logs estruturados com correlação por `request_id`, `project_id`, `user_id`.

## Trade-offs
- Poliglotismo aumenta complexidade operacional.
  - Mitigação: contratos de API internos versionados e documentação técnica por feature.
- Duas bases de dados (NeonDB + MongoDB) elevam custo cognitivo.
  - Mitigação: fronteira explícita de responsabilidade por domínio.

## Plano de entrega por fases
1. Fase 1 (MVP): upload/processamento PDF, chat RAG com fontes, histórico.
2. Fase 2: resumo estruturado e comparação entre documentos.
3. Fase 3: cache semântico otimizado, indexador público completo e métricas RAG.

## Métricas de validação
- Técnicas: latência p95, throughput, taxa de erro, tempo médio de processamento de PDF.
- RAG: faithfulness, answer relevancy, context recall, context precision.
