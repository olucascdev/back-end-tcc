# Guia de Integração BFF — Backend TCC

> Este documento orienta desenvolvedores do BFF (Next.js) a integrar o frontend com o backend existente, composto por serviços Go, Python e infraestrutura de IA.

---

## Sumário

1. [Visão Geral da Arquitetura](#1-visão-geral-da-arquitetura)
2. [Pré-requisitos de Infraestrutura](#2-pré-requisitos-de-infraestrutura)
3. [Endpoints do Go Gateway](#3-endpoints-do-go-gateway)
4. [Fluxos Detalhados](#4-fluxos-detalhados)
5. [O Que o Backend NÃO Faz](#5-o-que-o-backend-não-faz)
6. [Variáveis de Ambiente Relevantes](#6-variáveis-de-ambiente-relevantes)
7. [Exemplos Práticos (cURL)](#7-exemplos-práticos-curl)
8. [Contratos e Schemas](#8-contratos-e-schemas)
9. [Dicas e Boas Práticas](#9-dicas-e-boas-práticas)

---

## 1. Visão Geral da Arquitetura

O backend deste projeto funciona como um **orquestrador de IA** para processamento de documentos acadêmicos (PDFs), chat com contexto (RAG), sumarização e comparação de documentos.

### Componentes do backend

| Serviço | Tecnologia | Responsabilidade |
|---|---|---|
| **Go Gateway** | Go + Gin | Orquestração principal, rate limiting, cache semântico (Redis), fila de processamento de PDFs, circuit breaker. Expõe a API REST que o BFF consome. |
| **Python Agent** | FastAPI + Agno | Processamento de IA: extração de chunks de documentos, chat RAG com fontes, sumarização, comparação de documentos, pesquisa de lacunas (research gaps). Consumido **internamente** pelo Go Gateway — o BFF **não** fala diretamente com ele. |
| **Public Indexer** | Serviço separado | Indexação de documentos públicos (acervo aberto). Também consumido internamente pelo Go Gateway. |

### Papel do BFF

O BFF (Backend for Frontend) em Next.js é responsável por:

- **Autenticação**: login, registro, gestão de JWT dos usuários.
- **CRUD de entidades**: usuários, projetos, documentos (metadados).
- **Upload de arquivos**: envio de PDFs para o MinIO/S3.
- **Gestão de sessões de chat**: criação e manutenção de `session_id`.
- **Orquestração do frontend**: chamar o Go Gateway nos momentos certos e renderizar as respostas.

### Comunicação

```
┌─────────────┐       HTTP REST        ┌──────────────┐       interno       ┌────────────────┐
│   BFF       │ ──────────────────────► │  Go Gateway  │ ──────────────────► │  Python Agent  │
│  (Next.js)  │                         │  (orquestra) │                     │  (IA / Agno)   │
└─────────────┘                         └──────────────┘                     └────────────────┘
       │                                       │
       │                                       │       interno       ┌────────────────┐
       │                                       └────────────────────►│ Public Indexer │
       │                                                             └────────────────┘
       │
       ▼
┌─────────────┐
│  MinIO/S3   │  (upload de PDFs — acesso direto do BFF ou do browser)
└─────────────┘
```

> **Regra fundamental**: o BFF conversa **apenas** com o Go Gateway via HTTP REST. Todos os endpoints estão prefixados por `/api/v1`.

---

## 2. Pré-requisitos de Infraestrutura

Para que o BFF consiga se integrar corretamente, os seguintes pré-requisitos de rede e infraestrutura devem estar satisfeitos:

### 2.1 Acesso de rede ao Go Gateway

- O BFF precisa ter acesso HTTP ao serviço Go Gateway.
- Em desenvolvimento local, isso geralmente significa `http://localhost:<porta>`.
- Em produção, o Go Gateway deve estar atrás de um reverse proxy (Nginx, Traefik, etc.) com HTTPS.

### 2.2 Acesso ao MinIO/S3 para upload de PDFs

- O BFF (ou o browser diretamente, via presigned URL) precisa de acesso ao bucket MinIO/S3 para fazer upload dos PDFs.
- O backend **não** recebe uploads de arquivo diretamente — ele apenas recebe o `storage_key` (caminho do arquivo no bucket) após o upload ser concluído.
- Credenciais de acesso ao MinIO devem ser configuradas no BFF.

### 2.3 Endpoint de webhook (opcional, mas recomendado)

- Se o BFF quiser receber notificações assíncronas sobre o status de processamento de documentos, ele precisa expor um endpoint HTTP público (ou acessível pelo backend) que aceite requisições `POST`.
- Este endpoint será chamado pelo Go Gateway quando o processamento de um documento for concluído (com sucesso ou erro).
- O webhook é **best-effort**: se o endpoint do BFF estiver indisponível, o backend tentará algumas vezes e depois desistirá.

---

## 3. Endpoints do Go Gateway

Todos os endpoints abaixo estão prefixados por `/api/v1`.

> **Base URL exemplo**: `http://localhost:8080/api/v1`

---

### 3.1 Health Check

Verifica se o serviço está saudável e pronto para receber requisições.

#### `GET /health`

Retorna status geral do serviço.

**Response `200 OK`**:
```json
{
  "status": "ok"
}
```

#### `GET /health/ready`

Verifica se todas as dependências (banco de dados, Redis, Python Agent) estão conectadas e o serviço está pronto para processar requisições.

**Response `200 OK`**:
```json
{
  "status": "ready"
}
```

**Response `503 Service Unavailable`**:
```json
{
  "status": "not_ready",
  "checks": {
    "database": "ok",
    "redis": "error",
    "python_agent": "ok"
  }
}
```

---

### 3.2 Processar Documento

Envia um documento para processamento (extração de chunks, geração de embeddings, indexação).

#### `POST /documents/process`

**Descrição**: Enfileira um documento para processamento assíncrono. O backend retorna imediatamente com status `pending` e o processamento ocorre em background.

**Request Body**:

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `project_id` | `string` (UUID) | Sim | Identificador do projeto ao qual o documento pertence. Gerado pelo BFF. |
| `document_id` | `string` (UUID) | Sim | Identificador único do documento. Gerado pelo BFF. |
| `storage_key` | `string` | Sim | Caminho completo do arquivo PDF no bucket MinIO/S3. Ex: `uploads/projeto-x/documento.pdf`. |
| `source_type` | `string` | Não | Origem do documento. Default: `"user_upload"`. |
| `metadata` | `object` | Não | Metadados adicionais do documento (ex: título, autor, ano). |

**Exemplo de Request**:
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "storage_key": "uploads/projeto-x/artigo-machine-learning.pdf",
  "source_type": "user_upload",
  "metadata": {
    "title": "Artigo sobre Machine Learning",
    "author": "João Silva",
    "year": 2024
  }
}
```

**Response `202 Accepted`**:

| Campo | Tipo | Descrição |
|---|---|---|
| `document_id` | `string` (UUID) | Identificador do documento processado. |
| `status` | `string` | Status atual: `pending`, `processing`, `ready`, `error`. |
| `chunks_count` | `integer` (opcional) | Quantidade de chunks extraídos (presente quando `status` = `ready`). |
| `processed_at` | `string` (datetime, opcional) | Timestamp ISO 8601 do processamento (presente quando `status` = `ready`). |
| `error_message` | `string` (opcional) | Mensagem de erro (presente quando `status` = `error`). |

**Exemplo de Response (pending)**:
```json
{
  "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "status": "pending"
}
```

**Exemplo de Response (ready)**:
```json
{
  "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "status": "ready",
  "chunks_count": 42,
  "processed_at": "2026-05-18T14:30:00Z"
}
```

**Exemplo de Response (error)**:
```json
{
  "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "status": "error",
  "error_message": "Falha ao extrair texto do PDF: arquivo corrompido"
}
```

**Códigos de status possíveis**:

| Código | Significado |
|---|---|
| `202` | Documento aceito e enfileirado para processamento. |
| `400` | Request inválido (campos obrigatórios ausentes, formato incorreto). |
| `500` | Erro interno do servidor. |

---

### 3.3 Chat RAG

Envia uma mensagem para o chat com contexto dos documentos do projeto (Retrieval-Augmented Generation).

#### `POST /chat`

**Descrição**: Envia uma pergunta/mensagem e recebe uma resposta da IA baseada nos documentos do projeto, com fontes citadas.

**Request Body**:

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `project_id` | `string` (UUID) | Sim | Identificador do projeto. |
| `session_id` | `string` | Sim | Identificador da sessão de conversa. Gerado pelo BFF. Usado para manter contexto entre mensagens. |
| `message` | `string` | Sim | A pergunta ou mensagem do usuário. |
| `filters` | `object` | Não | Filtros opcionais para a busca (ex: por documento específico, por data). |
| `retrieval_mode` | `string` | Não | Modo de busca: `"project_only"` (só documentos do projeto) ou `"project_plus_public"` (projeto + acervo público). Default: `"project_only"`. |

**Exemplo de Request**:
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": "sessao-abc-123",
  "message": "Quais são os principais métodos de extração de texto mencionados nos documentos?",
  "retrieval_mode": "project_only"
}
```

**Response `200 OK`**:

| Campo | Tipo | Descrição |
|---|---|---|
| `answer` | `string` | Resposta gerada pela IA. |
| `sources` | `array` de `Source` | Fontes utilizadas para gerar a resposta. |
| `session_id` | `string` | Identificador da sessão (eco do request). |
| `created_at` | `string` (datetime) | Timestamp ISO 8601 da resposta. |

**Objeto `Source`**:

| Campo | Tipo | Descrição |
|---|---|---|
| `document` | `string` | Nome ou identificador do documento fonte. |
| `page` | `integer` | Página do documento onde a informação foi encontrada. |
| `section` | `string` (opcional) | Seção do documento (ex: "Introdução", "Metodologia"). |
| `score` | `float` | Score de relevância da fonte (0.0 a 1.0). |
| `source_type` | `string` | Tipo da fonte: `"project_document"` ou `"public_library"`. |

**Exemplo de Response**:
```json
{
  "answer": "Os documentos mencionam três principais métodos de extração de texto: OCR para documentos digitalizados, extração direta de PDFs nativos e parsing de HTML para documentos web.",
  "sources": [
    {
      "document": "artigo-machine-learning.pdf",
      "page": 3,
      "section": "Metodologia",
      "score": 0.92,
      "source_type": "project_document"
    },
    {
      "document": "guia-processamento-texto.pdf",
      "page": 12,
      "score": 0.85,
      "source_type": "project_document"
    }
  ],
  "session_id": "sessao-abc-123",
  "created_at": "2026-05-18T14:35:00Z"
}
```

**Códigos de status possíveis**:

| Código | Significado |
|---|---|
| `200` | Resposta gerada com sucesso. |
| `400` | Request inválido. |
| `500` | Erro interno do servidor. |

---

### 3.4 Sumarizar Documento

Gera um resumo estruturado de um documento processado.

#### `POST /summarize`

**Descrição**: Solicita a sumarização de um documento já processado. A IA gera um resumo com campos como objetivo, metodologia, resultados e conclusão.

**Request Body**:

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `document_id` | `string` (UUID) | Sim | Identificador do documento a ser sumarizado. |
| `project_id` | `string` (UUID) | Sim | Identificador do projeto. |
| `format` | `string` | Não | Formato do resumo. Default: `"structured"`. |

**Exemplo de Request**:
```json
{
  "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "format": "structured"
}
```

**Response `200 OK`**:

| Campo | Tipo | Descrição |
|---|---|---|
| `document_id` | `string` (UUID) | Identificador do documento sumarizado. |
| `summary` | `object` | Objeto com chaves como `objective`, `methodology`, `results`, `conclusion`. |
| `created_at` | `string` (datetime) | Timestamp ISO 8601 da sumarização. |

**Exemplo de Response**:
```json
{
  "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "summary": {
    "objective": "Investigar a eficácia de modelos de linguagem grandes na extração de informações de documentos acadêmicos.",
    "methodology": "Revisão sistemática de 45 artigos publicados entre 2020 e 2024, com análise comparativa de métricas de precisão e recall.",
    "results": "Modelos baseados em transformers alcançaram F1-score médio de 0.89, superando abordagens tradicionais em 15%.",
    "conclusion": "A adoção de LLMs para extração de informação em documentos acadêmicos é viável e recomendada, com ressalvas sobre custo computacional."
  },
  "created_at": "2026-05-18T14:40:00Z"
}
```

**Códigos de status possíveis**:

| Código | Significado |
|---|---|
| `200` | Sumarização gerada com sucesso. |
| `400` | Request inválido. |
| `404` | Documento não encontrado ou não processado. |
| `500` | Erro interno do servidor. |

---

### 3.5 Comparar Documentos

Compara múltiplos documentos de um projeto sobre um tema específico.

#### `POST /compare`

**Descrição**: Solicita uma comparação entre dois ou mais documentos do projeto, focada em um tema definido.

**Request Body**:

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `project_id` | `string` (UUID) | Sim | Identificador do projeto. |
| `document_ids` | `array` de UUID | Sim | Lista de identificadores dos documentos a comparar. Mínimo: 2. |
| `theme` | `string` | Sim | Tema ou foco da comparação. |

**Exemplo de Request**:
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "document_ids": [
    "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "6ba7b811-9dad-11d1-80b4-00c04fd430c8"
  ],
  "theme": "Métodos de extração de texto"
}
```

**Response `200 OK`**:

| Campo | Tipo | Descrição |
|---|---|---|
| `project_id` | `string` (UUID) | Identificador do projeto. |
| `comparison` | `object` | Objeto com a comparação gerada pela IA (estrutura varia conforme o tema). |
| `sources` | `array` de `Source` | Fontes utilizadas na comparação. |
| `created_at` | `string` (datetime) | Timestamp ISO 8601 da comparação. |

**Exemplo de Response**:
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "comparison": {
    "similarities": "Ambos os documentos abordam OCR como técnica fundamental, porém com abordagens diferentes de pré-processamento.",
    "differences": "O documento A foca em documentos digitalizados antigos, enquanto o documento B trata de PDFs nativos modernos.",
    "synthesis": "A combinação das duas abordagens pode cobrir um espectro mais amplo de tipos de documento."
  },
  "sources": [
    {
      "document": "artigo-machine-learning.pdf",
      "page": 3,
      "score": 0.91,
      "source_type": "project_document"
    },
    {
      "document": "guia-processamento-texto.pdf",
      "page": 7,
      "score": 0.88,
      "source_type": "project_document"
    }
  ],
  "created_at": "2026-05-18T14:45:00Z"
}
```

**Códigos de status possíveis**:

| Código | Significado |
|---|---|
| `200` | Comparação gerada com sucesso. |
| `400` | Request inválido (menos de 2 documentos, campos ausentes). |
| `500` | Erro interno do servidor. |

---

### 3.6 Pesquisar Lacunas (Research Gaps)

Identifica lacunas de pesquisa nos documentos do projeto.

#### `POST /research/gaps`

**Descrição**: Analisa os documentos do projeto e identifica lacunas de pesquisa (research gaps) sobre um tema específico.

**Request Body**:

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `project_id` | `string` (UUID) | Sim | Identificador do projeto. |
| `theme` | `string` | Não | Tema para busca de lacunas. Default: `""` (analisa todos os temas). |

**Exemplo de Request**:
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "theme": "Eficiência computacional de LLMs"
}
```

**Response `200 OK`**:

| Campo | Tipo | Descrição |
|---|---|---|
| `project_id` | `string` (UUID) | Identificador do projeto. |
| `gaps` | `array` de `ResearchGapItem` | Lista de lacunas identificadas. |
| `created_at` | `string` (datetime) | Timestamp ISO 8601 da análise. |

**Objeto `ResearchGapItem`**:

| Campo | Tipo | Descrição |
|---|---|---|
| `gap_title` | `string` | Título da lacuna identificada. |
| `why_gap` | `string` | Explicação do porquê isso é uma lacuna. |
| `evidence_sources` | `array` de `Source` | Fontes que evidenciam a lacuna. |
| `suggested_questions` | `array` de `string` | Perguntas sugeridas para explorar a lacuna. |
| `confidence` | `string` | Nível de confiança: `"low"`, `"medium"` ou `"high"`. |

**Exemplo de Response**:
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "gaps": [
    {
      "gap_title": "Falta de benchmarks padronizados para extração de texto em PDFs acadêmicos",
      "why_gap": "Nenhum dos documentos analisados propõe ou utiliza um benchmark comum para comparar métodos de extração, o que dificulta a reprodutibilidade.",
      "evidence_sources": [
        {
          "document": "artigo-machine-learning.pdf",
          "page": 15,
          "section": "Discussão",
          "score": 0.78,
          "source_type": "project_document"
        }
      ],
      "suggested_questions": [
        "Como criar um benchmark padronizado para extração de texto?",
        "Quais métricas são mais adequadas para avaliar a qualidade da extração?"
      ],
      "confidence": "high"
    }
  ],
  "created_at": "2026-05-18T14:50:00Z"
}
```

**Códigos de status possíveis**:

| Código | Significado |
|---|---|
| `200` | Análise de lacunas gerada com sucesso. |
| `400` | Request inválido. |
| `500` | Erro interno do servidor. |

---

### 3.7 Status de Job

Consulta o status de um job de processamento de documento.

#### `GET /documents/jobs/{job_id}`

**Descrição**: Retorna o status atual de um job de processamento. O `job_id` é o mesmo `document_id` enviado no request de processamento.

**Path Parameters**:

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `job_id` | `string` (UUID) | Identificador do job (igual ao `document_id`). |

**Response `200 OK`**:

Mesmo schema de `ProcessDocumentResponse` (ver seção 3.2).

**Exemplo de Response**:
```json
{
  "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "status": "processing"
}
```

**Códigos de status possíveis**:

| Código | Significado |
|---|---|
| `200` | Status do job retornado com sucesso. |
| `404` | Job não encontrado. |
| `500` | Erro interno do servidor. |

---

## 4. Fluxos Detalhados

### Fluxo 1: Upload e Processamento de PDF

Este fluxo descreve o caminho completo desde o upload de um PDF pelo usuário até o documento estar pronto para consulta via chat.

```
┌─────────┐     ┌─────┐     ┌────────────┐     ┌──────────────┐
│ Usuário │     │ BFF │     │  MinIO/S3  │     │  Go Gateway  │
└────┬────┘     └──┬──┘     └─────┬──────┘     └──────┬───────┘
     │              │              │                   │
     │ 1. Escolhe   │              │                   │
     │    PDF       │              │                   │
     │─────────────►│              │                   │
     │              │ 2. Upload    │                   │
     │              │─────────────►│                   │
     │              │              │                   │
     │              │ 3. Retorna   │                   │
     │              │    storage_key                   │
     │              │◄─────────────│                   │
     │              │              │                   │
     │              │ 4. Gera      │                   │
     │              │    document_id (UUID)            │
     │              │              │                   │
     │              │ 5. POST /documents/process       │
     │              │──────────────────────────────────►│
     │              │              │                   │
     │              │ 6. 202 Accepted (status: pending)│
     │              │◄─────────────────────────────────│
     │              │              │                   │
     │              │              │    Processamento  │
     │              │              │    em background  │
     │              │              │                   │
     │              │ 7a. Polling  │                   │
     │              │    GET /jobs/{id}                │
     │              │──────────────────────────────────►│
     │              │              │                   │
     │              │ 7b. Ou aguarda webhook ◄─────────│
     │              │              │                   │
     │ 8. Atualiza  │              │                   │
     │    UI        │              │                   │
     │◄─────────────│              │                   │
```

**Passo a passo**:

1. **Usuário escolhe PDF** no frontend (input file).
2. **BFF faz upload** do PDF para o MinIO/S3 (ou gera uma presigned URL para o browser fazer upload direto).
3. **MinIO retorna** o `storage_key` — o caminho completo do arquivo no bucket. Exemplo: `uploads/projeto-x/artigo-machine-learning.pdf`.
4. **BFF gera** um `document_id` (UUIDv4). O `project_id` já foi gerado anteriormente quando o BFF criou o projeto.
5. **BFF chama** `POST /api/v1/documents/process` com `project_id`, `document_id`, `storage_key` e metadados opcionais.
6. **Backend responde** `202 Accepted` com `status: "pending"`.
7. **BFF monitora** o status de duas formas:
   - **Polling**: faz `GET /api/v1/documents/jobs/{document_id}` a cada 3-5 segundos até o status mudar para `ready` ou `error`.
   - **Webhook**: aguarda o backend enviar um POST para o endpoint de webhook configurado no BFF.
8. **BFF atualiza** a interface do usuário com o resultado (sucesso ou erro).

---

### Fluxo 2: Chat RAG

Este fluxo descreve a interação do usuário com o chat baseado nos documentos do projeto.

```
┌─────────┐     ┌─────┐     ┌──────────────┐
│ Usuário │     │ BFF │     │  Go Gateway  │
└────┬────┘     └──┬──┘     └──────┬───────┘
     │              │               │
     │ 1. Digita    │               │
     │    pergunta  │               │
     │─────────────►│               │
     │              │ 2. POST /chat │
     │              │──────────────►│
     │              │               │
     │              │    IA processa│
     │              │    (busca RAG,│
     │              │     gera resp)│
     │              │               │
     │              │ 3. Resposta   │
     │              │    + fontes   │
     │              │◄──────────────│
     │              │               │
     │ 4. Renderiza │               │
     │    resposta  │               │
     │    + fontes  │               │
     │◄─────────────│               │
```

**Passo a passo**:

1. **Usuário envia** uma mensagem/pergunta no frontend.
2. **BFF chama** `POST /api/v1/chat` passando:
   - `project_id`: UUID do projeto atual.
   - `session_id`: identificador da sessão (gerado pelo BFF na primeira mensagem e reutilizado nas subsequentes).
   - `message`: texto da pergunta.
   - `retrieval_mode`: `"project_only"` ou `"project_plus_public"`.
3. **Backend processa** a requisição: busca chunks relevantes nos embeddings, envia para a IA gerar a resposta com contexto, retorna a resposta + fontes.
4. **BFF renderiza** a resposta e as fontes no frontend (ex: cards com documento, página e score de cada fonte).

---

### Fluxo 3: Webhook de Status

Este fluxo descreve como o backend notifica o BFF sobre mudanças no status de processamento de documentos.

```
┌──────────────┐          ┌─────┐
│  Go Gateway  │          │ BFF │
└──────┬───────┘          └──┬──┘
       │                     │
       │ 1. Processamento    │
       │    concluído        │
       │                     │
       │ 2. POST {WEBHOOK_URL}│
       │    com payload      │
       │    + assinatura     │
       │────────────────────►│
       │                     │
       │                     │ 3. Verifica assinatura
       │                     │    HMAC-SHA256
       │                     │
       │                     │ 4. Atualiza status
       │                     │    no banco do BFF
       │                     │
       │ 5. 200 OK           │
       │◄────────────────────│
```

**Detalhes do webhook**:

- **URL**: configurada no backend via variável de ambiente `WEBHOOK_URL`.
- **Método**: `POST`.
- **Content-Type**: `application/json`.

**Payload**:

| Campo | Tipo | Descrição |
|---|---|---|
| `document_id` | `string` (UUID) | Identificador do documento. |
| `project_id` | `string` (UUID) | Identificador do projeto. |
| `status` | `string` | Status final: `"ready"` ou `"error"`. |
| `timestamp` | `string` (datetime) | Timestamp ISO 8601 do evento. |
| `error_message` | `string` (opcional) | Mensagem de erro (presente se `status` = `"error"`). |
| `metadata` | `object` (opcional) | Metadados adicionais. |

**Exemplo de Payload**:
```json
{
  "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ready",
  "timestamp": "2026-05-18T14:32:00Z",
  "metadata": {
    "chunks_count": 42
  }
}
```

**Header de assinatura**:

```
X-Webhook-Signature: sha256=<hmac_hex>
```

**Validação da assinatura (exemplo em TypeScript/Node.js)**:

```typescript
import crypto from 'crypto';

function verifyWebhookSignature(payload: string, signature: string, secret: string): boolean {
  const expected = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');

  return crypto.timingSafeEqual(
    Buffer.from(signature.replace('sha256=', '')),
    Buffer.from(expected)
  );
}

// Uso em um endpoint Next.js (App Router):
export async function POST(request: Request) {
  const body = await request.text();
  const signature = request.headers.get('X-Webhook-Signature') || '';
  const secret = process.env.WEBHOOK_SECRET!;

  if (!verifyWebhookSignature(body, signature, secret)) {
    return new Response('Invalid signature', { status: 401 });
  }

  const data = JSON.parse(body);
  // Processar o webhook...

  return new Response('OK', { status: 200 });
}
```

> **Importante**: o webhook é **best-effort**. Se o endpoint do BFF retornar erro ou estiver indisponível, o backend tentará algumas vezes (com retry) e depois desistirá. Por isso, o polling (Fluxo 1, opção 7a) é um fallback recomendado.

---

## 5. O Que o Backend NÃO Faz

É fundamental entender as responsabilidades que **não** são do backend e, portanto, **devem** ser implementadas pelo BFF:

| Responsabilidade | Quem faz | Detalhe |
|---|---|---|
| **Autenticação / Login / Registro** | BFF | O backend não possui sistema de autenticação. O BFF gerencia JWT, sessões de usuário, etc. |
| **CRUD de Projetos** | BFF | O backend não valida se um `project_id` existe. Ele aceita qualquer UUID válido. O BFF cria, atualiza e deleta projetos no seu próprio banco de dados. |
| **CRUD de Documentos (metadados)** | BFF | O backend só processa documentos. Metadados como título, autor, data de upload devem ser gerenciados pelo BFF. |
| **Upload de Arquivos** | BFF (ou browser) | O backend **não** recebe uploads. O BFF (ou o browser via presigned URL) faz upload para o MinIO/S3 e depois envia o `storage_key` para o backend. |
| **WebSocket / SSE** | N/A | O backend **não** suporta conexões em tempo real. O chat é HTTP síncrono (request/response). Para atualizações em tempo real, o BFF pode usar polling ou webhooks. |
| **Validação de `project_id`** | N/A | O backend aceita qualquer `project_id` válido (formato UUID). Não há verificação se o projeto existe no banco do BFF. |
| **Gestão de `session_id`** | BFF | O backend usa o `session_id` para manter contexto de conversa, mas não o cria nem o gerencia. O BFF é responsável por gerar e armazenar os IDs de sessão. |

---

## 6. Variáveis de Ambiente Relevantes

As seguintes variáveis de ambiente são relevantes para a integração entre BFF e backend:

### No Backend (Go Gateway)

| Variável | Descrição | Exemplo |
|---|---|---|
| `WEBHOOK_URL` | URL do endpoint do BFF que recebe notificações de status de processamento. | `https://bff.meusite.com/api/webhooks/document-status` |
| `WEBHOOK_SECRET` | Segredo compartilhado usado para assinar os payloads de webhook com HMAC-SHA256. Deve ser o mesmo configurado no BFF. | `um-segredo-bem-longo-e-aleatorio` |

### No BFF (Next.js)

| Variável | Descrição | Exemplo |
|---|---|---|
| `GATEWAY_BASE_URL` | URL base do Go Gateway. | `http://localhost:8080/api/v1` |
| `MINIO_ENDPOINT` | Endpoint do MinIO/S3 para upload de PDFs. | `http://localhost:9000` |
| `MINIO_ACCESS_KEY` | Chave de acesso ao MinIO. | `minioadmin` |
| `MINIO_SECRET_KEY` | Chave secreta do MinIO. | `minioadmin` |
| `MINIO_BUCKET_NAME` | Nome do bucket para uploads. | `tcc-documents` |
| `WEBHOOK_SECRET` | Mesmo segredo configurado no backend para validar assinaturas de webhook. | `um-segredo-bem-longo-e-aleatorio` |

---

## 7. Exemplos Práticos (cURL)

### 7.1 Processar Documento

```bash
curl -X POST http://localhost:8080/api/v1/documents/process \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "storage_key": "uploads/projeto-x/artigo-machine-learning.pdf",
    "source_type": "user_upload",
    "metadata": {
      "title": "Artigo sobre Machine Learning",
      "author": "João Silva",
      "year": 2024
    }
  }'
```

**Resposta esperada**:
```json
{
  "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "status": "pending"
}
```

---

### 7.2 Fazer Chat

```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "session_id": "sessao-abc-123",
    "message": "Quais são os principais métodos de extração de texto mencionados nos documentos?",
    "retrieval_mode": "project_only"
  }'
```

**Resposta esperada**:
```json
{
  "answer": "Os documentos mencionam três principais métodos de extração de texto...",
  "sources": [
    {
      "document": "artigo-machine-learning.pdf",
      "page": 3,
      "section": "Metodologia",
      "score": 0.92,
      "source_type": "project_document"
    }
  ],
  "session_id": "sessao-abc-123",
  "created_at": "2026-05-18T14:35:00Z"
}
```

---

### 7.3 Verificar Status de Job

```bash
curl -X GET http://localhost:8080/api/v1/documents/jobs/6ba7b810-9dad-11d1-80b4-00c04fd430c8
```

**Resposta esperada (processing)**:
```json
{
  "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "status": "processing"
}
```

**Resposta esperada (ready)**:
```json
{
  "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "status": "ready",
  "chunks_count": 42,
  "processed_at": "2026-05-18T14:32:00Z"
}
```

---

### 7.4 Sumarizar Documento

```bash
curl -X POST http://localhost:8080/api/v1/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "format": "structured"
  }'
```

---

### 7.5 Comparar Documentos

```bash
curl -X POST http://localhost:8080/api/v1/compare \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "document_ids": [
      "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
      "6ba7b811-9dad-11d1-80b4-00c04fd430c8"
    ],
    "theme": "Métodos de extração de texto"
  }'
```

---

### 7.6 Pesquisar Lacunas

```bash
curl -X POST http://localhost:8080/api/v1/research/gaps \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "theme": "Eficiência computacional de LLMs"
  }'
```

---

## 8. Contratos e Schemas

Os contratos completos (tipos Go e schemas Python) estão disponíveis no código-fonte do projeto:

| Serviço | Arquivo | Descrição |
|---|---|---|
| **Go Gateway** | `services/go-gateway/internal/contracts/v1/types.go` | Tipos Go que definem os requests e responses da API v1. |
| **Python Agent** | `services/python-agent/app/schemas/contracts_v1.py` | Schemas Pydantic que definem os contratos internos entre Go e Python. |

> Estes arquivos são a **fonte da verdade** para os contratos. Se houver divergência entre este documento e o código, o código prevalece.

---

## 9. Dicas e Boas Práticas

### 9.1 Geração de IDs

- **Sempre gere `document_id` e `project_id` no BFF** usando UUIDv4.
- O backend não gera IDs — ele apenas os recebe e os utiliza como referência.
- Exemplo em TypeScript: `crypto.randomUUID()` ou use a biblioteca `uuid`.

### 9.2 Sessões de Chat

- O `session_id` pode ser qualquer string única por conversa.
- Recomendação: use UUIDv4 para cada nova conversa.
- O backend usa o `session_id` para manter o contexto histórico da conversa (memória de mensagens anteriores).
- Se o usuário iniciar uma nova conversa, gere um novo `session_id`.

### 9.3 Modo de Recuperação (`retrieval_mode`)

- `"project_only"`: a IA busca contexto **apenas** nos documentos do projeto. Use este modo por padrão.
- `"project_plus_public"`: a IA busca contexto nos documentos do projeto **e** no acervo público indexado. Use quando o usuário quiser enriquecer a resposta com fontes externas.

### 9.4 Storage Key

- O `storage_key` deve ser o **caminho completo** do arquivo no bucket MinIO/S3.
- Exemplo: `uploads/projeto-x/subpasta/artigo.pdf`.
- Não inclua o nome do bucket — apenas o caminho dentro dele.
- Certifique-se de que o backend tenha acesso de leitura ao bucket.

### 9.5 Polling vs Webhook

- **Polling**: simples de implementar, mas gera requisições desnecessárias. Recomendado para projetos pequenos ou como fallback.
  - Intervalo sugerido: 3-5 segundos.
  - Timeout sugerido: 5 minutos (se o processamento demorar mais, algo pode estar errado).
- **Webhook**: mais eficiente, mas requer endpoint público e validação de assinatura.
- **Recomendação**: implemente ambos. Use webhook como principal e polling como fallback.

### 9.6 Tratamento de Erros

- Sempre verifique o código de status HTTP antes de parsear o response.
- Para `4xx`, exiba a mensagem de erro para o usuário (ex: "Documento não encontrado").
- Para `5xx`, exiba uma mensagem genérica (ex: "Erro interno. Tente novamente mais tarde") e registre o erro para investigação.

### 9.7 Rate Limiting

- O Go Gateway possui rate limiting embutido. Se o BFF receber `429 Too Many Requests`, implemente backoff exponencial antes de retry.

### 9.8 Timeouts

- Configure timeouts adequados no BFF para as chamadas ao gateway:
  - **Chat**: 30-60 segundos (a IA pode demorar para gerar a resposta).
  - **Processar documento**: 10 segundos (o request retorna imediatamente com `202`).
  - **Summarize/Compare/Research Gaps**: 30-60 segundos.

---

## Próximos Passos

1. **Configurar variáveis de ambiente** no BFF conforme a seção 6.
2. **Implementar o cliente HTTP** para o Go Gateway (recomendado: criar um módulo/service dedicado).
3. **Implementar o upload para MinIO** (direto do browser via presigned URL ou via BFF).
4. **Implementar o endpoint de webhook** para receber notificações assíncronas.
5. **Testar os fluxos** localmente com os exemplos de cURL da seção 7.
6. **Consultar os contratos** em `services/go-gateway/internal/contracts/v1/types.go` para detalhes de tipos.

---

> **Dúvidas?** Consulte o time de backend ou abra uma issue no repositório com a tag `bff-integration`.
