# Feature 3 — Contratos Internos v1 entre Servicos

## Contexto

Definir contratos tipados compartilhados entre o gateway Go e o agente Python.
Garantir que ambas as partes serializem/deserializem payloads com o mesmo
formato JSON, evitando erros de integracao em tempo de execucao.

## Decisoes Tecnicas

| Decisao | Motivo |
|---|---|
| Pydantic v2 (Python) | Validacao nativa, `model_dump_json`, pattern constraints |
| Structs Go com tags `json` | Compatibilidade direta com `encoding/json` |
| `uuid.UUID` como tipo de ID | Padrao cross-service, compativel com PostgreSQL |
| `omitempty` em Go / `Optional` em Python | Campos opcionais nao aparecem no JSON quando nulos |
| `datetime.now(UTC)` | Evita deprecacao de `datetime.utcnow()` no Python 3.12+ |
| `status` com regex `^(pending\|processing\|ready\|error)$` | Valida valores permitidos no lado Python |
| `document_ids` com `min_length=2` | Comparacao exige ao menos 2 documentos |

## Implementacao

### Arquivos criados

| Arquivo | Linguagem | Conteudo |
|---|---|---|
| `services/python-agent/app/schemas/contracts_v1.py` | Python | 10 modelos Pydantic |
| `services/python-agent/tests/test_contracts_v1.py` | Python | 39 testes unitarios |
| `services/go-gateway/internal/contracts/v1/types.go` | Go | 10 structs com tags json |
| `services/go-gateway/internal/contracts/v1/types_test.go` | Go | 14 testes de marshaling |

### Modelos/Structs

| Nome | Direcao | Campos obrigatorios |
|---|---|---|
| `ProcessDocumentRequest` | Go → Python | project_id, document_id, storage_key |
| `ProcessDocumentResponse` | Python → Go | document_id, status |
| `ChatRequest` | Go → Python | project_id, session_id, message |
| `ChatResponse` | Python → Go | answer, sources, session_id |
| `Source` | Ambos | document, page, score |
| `SummarizeRequest` | Go → Python | document_id, project_id |
| `SummarizeResponse` | Python → Go | document_id, summary |
| `CompareRequest` | Go → Python | project_id, document_ids (≥2), theme |
| `CompareResponse` | Python → Go | project_id, comparison, sources |
| `DocumentStatusWebhook` | Python → Go | document_id, project_id, status |

## Testes Executados

### Python (pytest 9.0.3, Pydantic 2.13)

```
39 passed in 0.08s
```

Cobertura por modelo:
- `Source`: 4 testes (valido minimo, completo, obrigatorio, json roundtrip)
- `ProcessDocumentRequest`: 4 testes
- `ProcessDocumentResponse`: 6 testes (inclui parametrizacao de 4 status + invalido)
- `ChatRequest`: 4 testes
- `ChatResponse`: 3 testes
- `SummarizeRequest`: 4 testes
- `SummarizeResponse`: 3 testes
- `CompareRequest`: 4 testes (inclui rejeicao de 1 documento)
- `CompareResponse`: 3 testes
- `DocumentStatusWebhook`: 4 testes

### Go (pendente)

Go toolchain nao disponivel na maquina de desenvolvimento atual.
Testes compilam e executam com `go test ./internal/contracts/v1/...`
quando o ambiente Go estiver configurado.

## Proximos Passos

1. Instalar Go toolchain e executar `go test ./internal/contracts/v1/...`
2. Criar handlers HTTP no gateway Go que usem esses structs como request/response
3. Criar endpoints FastAPI no agente Python que usem os schemas Pydantic
4. Adicionar validacao de `status` no lado Go (enum ou constante)
5. Gerar OpenAPI spec a partir dos contratos para documentacao
