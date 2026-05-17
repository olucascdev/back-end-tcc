## ADDED Requirements

### Requirement: Busca on-demand em fontes públicas com fallback
O sistema MUST prover busca sob demanda em fontes públicas acadêmicas quando o modo de recuperação for `project_plus_public`, retornando no máximo 5 referências relevantes por consulta, com fallback entre múltiplas fontes.

#### Scenario: Busca bem-sucedida no OpenAlex
- **WHEN** o usuário enviar uma mensagem com retrieval_mode="project_plus_public"
- **THEN** o sistema consulta a API do OpenAlex com a query do usuário e retorna até 5 resultados com título, autores, abstract e URL de acesso aberto

#### Scenario: Fallback para Unpaywall quando OpenAlex não tem URL
- **WHEN** o OpenAlex retornar um work sem URL de download
- **THEN** o sistema usa o DOI para consultar a API Unpaywall e obter o PDF open access

#### Scenario: Fallback para Google Books quando não há acesso aberto
- **WHEN** nem OpenAlex nem Unpaywall retornarem URL de download
- **THEN** o sistema consulta a Google Books API para obter preview/link do livro

#### Scenario: Limite de resultados e relevância
- **WHEN** a busca on-demand for executada
- **THEN** o sistema limita a no máximo 5 resultados e ordena por relevância (score do OpenAlex ou similar)

#### Scenario: Extração e chunking on-demand
- **WHEN** os resultados forem obtidos das fontes públicas
- **THEN** o sistema baixa o texto dos top-N resultados, aplica chunking e gera embeddings em tempo real

#### Scenario: Cache temporário em Redis
- **WHEN** embeddings on-demand forem gerados
- **THEN** o sistema armazena os chunks e embeddings no Redis com TTL de 1 hora para reutilização

#### Scenario: Integração com contexto do projeto
- **WHEN** o modo for project_plus_public
- **THEN** o sistema combina chunks dos documentos do projeto com chunks das fontes públicas para formar o contexto do RAG

#### Scenario: Fontes rastreáveis na resposta
- **WHEN** fontes públicas forem usadas na resposta
- **THEN** a resposta inclui metadados de fonte (título, autores, URL, fonte de origem) no array `sources`
