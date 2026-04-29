## Feature 6.0: Preflight Baseline

- [x] 6.0.1 Congelar métricas baseline do sistema (latência, throughput, cobertura de testes)
- [x] 6.0.2 Definir SLOs para chat RAG, processamento de documento e gateway
- [x] 6.0.3 Criar golden dataset mínimo (perguntas, contextos esperados, respostas de referência)
- [x] 6.0.4 Versionar golden dataset no repositório e documentar schema

## Feature 6.1: Public Library Consumption in Chat RAG

- [x] 6.1.1 Implementar `project_plus_public` retrieval mode no serviço Python
- [x] 6.1.2 Adicionar feature flag `ENABLE_PUBLIC_RETRIEVAL` (env var)
- [x] 6.1.3 Estender `PgVectorStore.search_similar_by_project()` para buscar também `source_type=public_library`
- [x] 6.1.4 Incluir `source_type` em cada fonte retornada no response de chat (project_document | public_library)
- [x] 6.1.5 Garantir que modo `project_only` permaneça como padrão

## Feature 6.2: Complete Test Suites

- [x] 6.2.1 Implementar testes unitários Go para rate limiting, circuit breaker, cache semântico e fila de PDF
- [x] 6.2.2 Implementar testes de integração Go para endpoints do gateway com dependências mockadas
- [x] 6.2.3 Implementar testes unitários Python para chunking, embeddings, chat RAG e memória de sessão
- [x] 6.2.4 Implementar testes de integração Python para endpoints FastAPI com DB de teste
- [x] 6.2.5 Implementar smoke e2e mínimo (health → process document → chat → assert sources)

## Feature 6.3: Load/Resilience Benchmark

- [x] 6.3.1 Criar endpoint `POST /benchmark/load` no gateway Go para iniciar teste de carga
- [x] 6.3.2 Coletar latência p50/p95/p99, throughput (req/s) e taxa de erro durante benchmark
- [x] 6.3.3 Simular degradação de dependência Python e medir comportamento do circuit breaker
- [x] 6.3.4 Simular degradação de NeonDB/Redis e medir fallback ou erro controlado
- [x] 6.3.5 Gerar relatório estruturado de benchmark com comparação contra baseline

## Feature 6.4: RAG Academic Evaluation

- [x] 6.4.1 Implementar pipeline de avaliação executável via CLI/script Python
- [x] 6.4.2 Calcular faithfulness por comparação entre resposta e contexto recuperado
- [x] 6.4.3 Calcular answer relevancy por similaridade semântica pergunta-resposta
- [x] 6.4.4 Calcular context precision (proporção de chunks relevantes recuperados)
- [x] 6.4.5 Calcular context recall (proporção de chunks relevantes do golden dataset recuperados)
- [x] 6.4.6 Garantir reprodutibilidade: seed fixa, modelo fixo, dataset versionado
- [x] 6.4.7 Exportar resultados em JSON/CSV e gerar sumário executivo

## Feature 6.5: Final Security/Ops Hardening

- [x] 6.5.1 Proteger endpoints administrativos (benchmark, métricas internas) com auth admin (JWT scope)
- [x] 6.5.2 Aplicar redação de dados sensíveis em logs (tokens, emails, conteúdo de documentos)
- [x] 6.5.3 Configurar alertas estruturados para threshold de erro e latência no gateway
- [x] 6.5.4 Criar runbooks para incidentes: circuit breaker aberto, fila de PDF congestionada, DB indisponível

## Feature 6.6: Quality Gates and Phase Closure

- [x] 6.6.1 Definir quality gate unificado: cobertura de testes ≥ threshold, benchmark dentro de SLO, evaluation score ≥ mínimo
- [x] 6.6.2 Gerar relatório de compliance com evidências de testes, benchmark e evaluation
- [x] 6.6.3 Documentar riscos residuais e mitigações planejadas pós-TCC
- [x] 6.6.4 Atualizar README e docs de arquitetura com estado final da Phase 6
