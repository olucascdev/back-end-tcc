> Fase 5 concluida em 2026-04-29

## 5.0 Preflight tecnico e alinhamento de schema
- [x] 5.0.1 Validar e documentar schema vetorial unificado (colunas, tipos, metadata JSONB)
- [x] 5.0.2 Resolver divergencia de nome de tabela: padronizar `document_embeddings` em migracao e runtime
- [x] 5.0.3 Definir contrato de metadata obrigatorio para embeddings publicos (`source_type`, `source_provider`, `source_id`, `artifact_key`, `checksum`)
- [x] 5.0.4 Definir politica de deduplicacao por livro (chaves estaveis) e por chunk (fingerprint)

## 5.1 Bootstrap real do servico public-indexer
- [x] 5.1.1 Implementar estrutura em camadas (`api`, `application`, `domain`, `infrastructure`, `core`)
- [x] 5.1.2 Implementar `GET /health` com checagem de MongoDB, PostgreSQL, MinIO, Redis
- [x] 5.1.3 Implementar `POST /admin/index/run` para disparo manual de job
- [x] 5.1.4 Implementar `GET /admin/index/jobs/{job_id}` para consulta de status
- [x] 5.1.5 Configurar `Settings` (Pydantic) e lifecycle de conexoes
- [x] 5.1.6 Servico sobe localmente e health responde com todas as dependencias

## 5.2 Ingestao de catalogo publico (metadados)
- [x] 5.2.1 Implementar cliente Open Library API com normalizacao de campos
- [x] 5.2.2 Implementar cliente Project Gutenberg API com normalizacao de campos
- [x] 5.2.3 Normalizar titulo, autores, idioma, assuntos, ids de origem, formatos
- [x] 5.2.4 Implementar upsert em `books` com estado `indexed=false` para itens novos
- [x] 5.2.5 Implementar atualizacao para `indexed=false` e limpeza de status anterior quando item for alterado
- [x] 5.2.6 Implementar chaves de deduplicacao estaveis (`gutenberg_id`, `ol_key`, fallback hash)
- [x] 5.2.7 Ciclo de sync nao duplica livro logico

## 5.3 Download e armazenamento de artefatos
- [x] 5.3.1 Implementar seletor de formato com prioridade configuravel (padrao: txt > epub > pdf)
- [x] 5.3.2 Implementar download com timeout e retry seguro
- [x] 5.3.3 Persistir artefato no MinIO/S3 com chave deterministica (`provider/source_id/version`)
- [x] 5.3.4 Calcular e persistir `checksum` para controle de mudanca de conteudo
- [x] 5.3.5 Atualizar referencia `artifact_key` e `checksum` no MongoDB
- [x] 5.3.6 Isolar falhas de download por item (nao quebrar lote inteiro)

## 5.4 Geracao de embeddings publicos
- [x] 5.4.1 Implementar extracao de texto dos artefatos (txt/epub/pdf)
- [x] 5.4.2 Implementar chunking com parametros configuraveis
- [x] 5.4.3 Implementar geracao de embeddings em lote
- [x] 5.4.4 Persistir vetores no NeonDB/pgvector com metadata completa de origem
- [x] 5.4.5 Garantir `source_type=public_library` em 100% dos registros da fase
- [x] 5.4.6 Atualizar `indexed=true` e `indexed_at` no MongoDB apenas apos persistencia vetorial bem-sucedida

## 5.5 Idempotencia, retry e agendamento
- [x] 5.5.1 Implementar fingerprint de conteudo (`source_id + checksum + chunk_version`) para evitar duplicacao vetorial
- [x] 5.5.2 Implementar retry com backoff exponencial e jitter para erros transientes
- [x] 5.5.3 Implementar registro de falhas finais por item para reprocessamento posterior
- [x] 5.5.4 Implementar agendamento periodico via `SYNC_INTERVAL_MINUTES`
- [x] 5.5.5 Implementar lock distribuido Redis por job para evitar overlap de execucoes
- [x] 5.5.6 Reexecucao do mesmo lote nao cria duplicidade de embeddings
- [x] 5.5.7 Falha transiente recupera automaticamente dentro da politica de retry
- [x] 5.5.8 Execucao concorrente bloqueada por lock valido

## 5.6 Observabilidade e operacao
- [x] 5.6.1 Expor metrica `public_indexer_runs_total`
- [x] 5.6.2 Expor metrica `public_indexer_run_duration_seconds`
- [x] 5.6.3 Expor metrica `public_books_fetched_total`
- [x] 5.6.4 Expor metrica `public_books_indexed_total`
- [x] 5.6.5 Expor metrica `public_indexer_failures_total`
- [x] 5.6.6 Implementar logs estruturados com `request_id`, `job_id`, `source_provider`, `source_id`, `stage`
- [x] 5.6.7 Emitir relatorio de fim de job com totais: novos, atualizados, ignorados, indexados, falhos
- [x] 5.6.8 Validar que metricas sao consumiveis e logs permitem auditoria completa por job
