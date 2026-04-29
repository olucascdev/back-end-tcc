# Feature 4.3 — Sugestão de Lacunas de Pesquisa

**Data:** 2026-04-29
**Status:** Implementada e testada

## Contexto

Feature 4.3 implementa sugestão automática de lacunas de pesquisa baseada no corpus de documentos do projeto. O serviço analisa a cobertura temática dos documentos processados e identifica áreas subexploradas, gerando recomendações estruturadas com nível de confiança e fontes de evidência.

## Decisões Técnicas

### Arquitetura de endpoints

| Camada | Endpoint | Responsabilidade |
|---|---|---|
| Python (FastAPI) | `POST /api/v1/research/gaps` | Análise heurística do corpus, geração de lacunas |
| Go (Gin) | `POST /api/v1/documents/research/gaps` | Proxy com validação de `project_id`, rate limiting, circuit breaker |

### ResearchGapService

Serviço de domínio com heurística de cobertura temática:

- **Análise de frequência temática**: identifica temas com baixa representação no corpus.
- **Cálculo de confidence**: `low`, `medium` ou `high` baseado na densidade de evidências e consistência cruzada entre documentos.
- **Fallback para corpus vazio**: retorna lista vazia de gaps com status informativo, sem erro.

### Estrutura de saída

```json
{
  "gaps": [
    {
      "gap_title": "string",
      "why_gap": "string",
      "evidence_sources": ["string"],
      "suggested_questions": ["string"],
      "confidence": "low | medium | high"
    }
  ]
}
```

### Contratos versionados

- Contratos Go/Python versionados em **v1**, sem breaking change em relação às features 4.1 e 4.2.
- DTOs Go definidos em `internal/contracts/v1/types.go`.
- Schemas Python em `app/schemas/contracts_v1.py`.

## Implementação

### Arquivos criados

| Arquivo | Descrição |
|---|---|
| `app/domain/research_gap_service.py` | Serviço de domínio com heurística de lacunas e cálculo de confidence |
| `app/api/v1/endpoints/research.py` | Endpoint FastAPI para `/research/gaps` |
| `tests/test_research_gap_service.py` | Testes unitários do serviço (9 testes) |
| `internal/contracts/v1/types.go` | DTOs Go para ResearchGapRequest/Response |
| `internal/client/python/client.go` | Método `ResearchGaps` no cliente Python |
| `internal/api/v1/handlers/proxy.go` | Handler `ProxyResearchGaps` |
| `internal/api/v1/router.go` | Rota `POST /documents/research/gaps` |

### Arquivos modificados

| Arquivo | Alteração |
|---|---|
| `app/schemas/contracts_v1.py` | Adicionados schemas `ResearchGapRequest`, `ResearchGapResponse`, `ResearchGapItem` |
| `app/api/v1/router.py` | Registro do router de pesquisa |
| `tests/test_api_v1.py` | Testes de integração do endpoint de pesquisa |
| `internal/contracts/v1/types_test.go` | Testes de serialização dos DTOs Go |
| `internal/client/python/client_test.go` | Testes do método `ResearchGaps` |
| `internal/api/v1/handlers/proxy_test.go` | Testes do handler proxy |

## Testes Executados

- **Total:** 135 passed, 0 failed
- **Testes específicos de research gap:** 9
  - Serviço com corpus populado → retorna gaps com confidence
  - Serviço com corpus vazio → retorna lista vazia (fallback)
  - Cálculo de confidence `low`, `medium`, `high`
  - Validação de estrutura de saída
  - Endpoint FastAPI responde corretamente
  - Handler Go proxy encaminha requisição
  - DTOs Go serializam/desserializam corretamente

## Próximos Passos

1. Avaliar precisão das lacunas sugeridas com corpus real de projetos acadêmicos.
2. Ajustar thresholds de confidence com base em feedback de usuários.
3. Considerar integração com embeddings para detecção semântica de lacunas (evolução futura).
