# Feature 5.3 - Artefatos e Armazenamento MinIO

**Data:** 2026-04-29
**Status:** Implementado

## Contexto

Com o catalogo ingerido (Feature 5.2), e necessario baixar os artefatos digitais (TXT, EPUB, PDF) das fontes publicas, validar integridade e armazenar no MinIO/S3. Isso desacopla a fonte externa do pipeline de embeddings e permite reprocessamento sem re-download.

## Decisoes Tecnicas

### ArtifactStorageService

- Abstracao `ArtifactStorageService` para upload/download/listagem no MinIO.
- Selecao de formato: preferencia por TXT > EPUB > PDF (mais facil extracao de texto).
- Download com streaming e barra de progresso logica (bytes lidos / total esperado).
- Checksum SHA-256 calculado no stream; validado antes do upload.
- Chave no MinIO: `artifacts/{source_provider}/{source_id}/{format}/{filename}`.
- Metadata do objeto: `content-type`, `checksum-sha256`, `source_url`, `downloaded_at`.

### ArtifactProcessorUseCase

- Orquestra o fluxo completo: seleciona formato, download, checksum, upload MinIO, atualiza catalogo.
- Idempotencia: se artefato ja existir no MinIO com mesmo checksum, pula download.
- Fallback de formato: se TXT nao disponivel, tenta EPUB; se EPUB falhar, tenta PDF.
- Registro de resultado no `JobStore` vinculado ao `job_id`.

## Implementacao

### Arquivos Criados/Modificados

| Arquivo | Acao | Descricao |
|---------|------|-----------|
| `app/infrastructure/artifact_storage.py` | Criado | ArtifactStorageService com upload stream, download, checksum SHA-256, selecao de formato |
| `app/application/artifact_processor.py` | Criado | ArtifactProcessorUseCase com selecao de formato, idempotencia por checksum, fallback, registro no JobStore |
| `app/domain/models.py` | Modificado | Adicionados `ArtifactRecord`, `ArtifactFormat` enums, `checksum` em BookMetadata |
| `app/infrastructure/clients.py` | Modificado | Adicionado metodo `get_minio_client()` com bucket auto-criacao |
| `app/core/config.py` | Modificado | Adicionadas variaveis `ARTIFACT_MAX_SIZE`, `ARTIFACT_PREFERRED_FORMATS` |
| `tests/test_artifact_storage.py` | Criado | 17 testes: upload stream, download, checksum match/mismatch, selecao formato, metadata, not found, presigned url |
| `tests/test_artifact_processor.py` | Criado | 8 testes: fluxo completo, idempotencia, fallback formato, checksum fail, job registro, erro rede, skip existente, batch |

## Testes Executados

```
$ pytest services/public-indexer/tests/test_artifact_storage.py -v
17 passed in 0.55s

$ pytest services/public-indexer/tests/test_artifact_processor.py -v
8 passed in 0.38s

---
Total Feature 5.3: 25 passed
```

## Proximos Passos

- **Feature 5.4**: Extracao de texto dos artefatos, chunking e geracao de embeddings no pgvector.

## Riscos Residuais

- Artefatos muito grandes (>100MB) podem estourar memoria em stream mal configurado — validar `ARTIFACT_MAX_SIZE` rigorosamente.
- MinIO em desenvolvimento usa single-node — em producao requer cluster e lifecycle policy.
