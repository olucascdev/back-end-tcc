"""
Servico de dominio para resumo estruturado de documentos academicos.

Responsavel por:
- Gerar embedding de query fixa para busca de chunks
- Buscar chunks similares no pgvector filtrados por project_id e document_id
- Montar contexto a partir dos chunks recuperados
- Chamar LLM com prompt academico deterministico
- Fazer parsing da resposta para garantir estrutura com 4 chaves
- Retornar SummarizeResponse estruturado
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import Settings
from app.infrastructure.database.pgvector_store import PgVectorStore
from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder
from app.schemas.contracts_v1 import SummarizeResponse

logger = logging.getLogger(__name__)

# Query fixa usada para buscar chunks relevantes para resumo
SUMMARIZE_QUERY = "summarize structured academic document"

# Chaves esperadas no resumo estruturado
SUMMARY_KEYS = ["objective", "methodology", "results", "conclusion"]

# Mensagem padrao quando nao ha contexto suficiente
INSUFFICIENT_CONTEXT = "Contexto insuficiente para gerar resumo."

# Valor padrao quando chave nao foi identificada na resposta do LLM
NOT_IDENTIFIED = "Nao identificado"

# Prompt academico deterministico para geracao de resumo estruturado
SUMMARIZE_PROMPT_TEMPLATE = (
    "Voce e um assistente especializado em analisar documentos academicos. "
    "Com base no contexto fornecido abaixo, gere um resumo estruturado contendo "
    "exatamente as seguintes quatro secoes:\n"
    "- objective: qual o objetivo principal do documento\n"
    "- methodology: qual metodologia foi utilizada\n"
    "- results: quais foram os resultados principais\n"
    "- conclusion: qual a conclusao do trabalho\n\n"
    "Retorne APENAS um JSON valido com essas quatro chaves, sem texto adicional. "
    "Exemplo de formato:\n"
    '{{"objective": "...", "methodology": "...", "results": "...", "conclusion": "..."}}\n\n'
    "Contexto:\n{context}"
)

# Limite padrao de tokens para o contexto (aproximacao: 1 token ~ 4 chars)
DEFAULT_MAX_CONTEXT_TOKENS = 4000


class SummarizeService:
    """Orquestra fluxo de resumo estruturado: embedding → busca → contexto → LLM → parsing."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedder: OpenAIEmbedder | None = None,
        vector_store: PgVectorStore | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._embedder = embedder or OpenAIEmbedder(self._settings)
        self._vector_store = vector_store or PgVectorStore(self._settings)

    def summarize(
        self,
        project_id: str,
        document_id: str,
    ) -> SummarizeResponse:
        """Gera resumo estruturado de um documento especifico dentro de um projeto.

        Fluxo:
        1. Gera embedding da query fixa
        2. Busca chunks similares no pgvector filtrando por project_id
        3. Filtra chunks onde metadata->>'document_id' == document_id
        4. Monta contexto com os chunks recuperados (limite de tokens)
        5. Chama LLM com prompt academico deterministico
        6. Faz parsing da resposta para garantir 4 chaves
        7. Se < 1 chunk, retorna com mensagem de contexto insuficiente

        Args:
            project_id: identificador do projeto para filtrar documentos.
            document_id: identificador do documento a ser resumido.

        Returns:
            SummarizeResponse com summary contendo objective, methodology,
            results e conclusion.
        """
        # 1. Gera embedding da query fixa
        logger.info(
            "Iniciando resumo: project_id=%s, document_id=%s",
            project_id,
            document_id,
        )
        query_embedding = self._embedder.embed_query(SUMMARIZE_QUERY)

        # 2. Busca chunks similares no pgvector
        chunks = self._vector_store.search_similar_by_project(
            project_id=project_id,
            query_embedding=query_embedding,
            top_k=10,
            min_score=0.5,
        )

        # 3. Filtra chunks por document_id especifico
        filtered_chunks = [
            chunk
            for chunk in chunks
            if chunk.get("metadata", {}).get("document_id") == document_id
        ]

        logger.info(
            "Chunks recuperados: %d total, %d filtrados por document_id=%s",
            len(chunks),
            len(filtered_chunks),
            document_id,
        )

        # 4. Se nao ha chunks suficientes, retorna fallback
        if len(filtered_chunks) < 1:
            logger.warning(
                "Contexto insuficiente para resumo: project_id=%s, document_id=%s",
                project_id,
                document_id,
            )
            return SummarizeResponse(
                document_id=document_id,
                summary={
                    "objective": INSUFFICIENT_CONTEXT,
                    "methodology": INSUFFICIENT_CONTEXT,
                    "results": INSUFFICIENT_CONTEXT,
                    "conclusion": INSUFFICIENT_CONTEXT,
                },
            )

        # 5. Monta contexto com limite de tokens
        context = self._build_context(filtered_chunks)

        # 6. Chama LLM com prompt deterministico
        raw_response = self._call_llm(context)

        # 7. Faz parsing da resposta para garantir estrutura
        summary = self._parse_response(raw_response)

        logger.info(
            "Resumo gerado com sucesso: project_id=%s, document_id=%s",
            project_id,
            document_id,
        )

        return SummarizeResponse(
            document_id=document_id,
            summary=summary,
        )

    def _build_context(self, chunks: list[dict[str, Any]]) -> str:
        """Monta bloco de contexto a partir dos chunks recuperados.

        Aplica limite de tokens para evitar exceder contexto do LLM.
        Aproximacao: 1 token ~ 4 caracteres.

        Args:
            chunks: lista de chunks com content, metadata e score.

        Returns:
            String formatada com contexto para o prompt.
        """
        max_chars = self._settings.MAX_CONTEXT_TOKENS * 4
        parts: list[str] = []
        total_chars = 0

        for idx, chunk in enumerate(chunks, start=1):
            meta = chunk.get("metadata", {})
            doc_id = meta.get("document_id", "desconhecido")
            page = meta.get("page_number", "?")
            chunk_text = (
                f"[Fonte {idx}] Documento: {doc_id}, Pagina: {page}\n"
                f"Conteudo: {chunk['content']}"
            )

            if total_chars + len(chunk_text) > max_chars and parts:
                # Ultrapassou limite; para de adicionar chunks
                logger.debug(
                    "Limite de contexto atingido (%d chars), %d chunks incluidos",
                    max_chars,
                    len(parts),
                )
                break

            parts.append(chunk_text)
            total_chars += len(chunk_text)

        return "\n\n".join(parts)

    def _call_llm(self, context: str) -> str:
        """Chama LLM com contexto e retorna resposta bruta.

        Usa OpenAI API com fallback mock para desenvolvimento.
        Temperatura 0.2 para respostas deterministicas.

        Args:
            context: contexto montado a partir dos chunks.

        Returns:
            Resposta bruta do LLM.
        """
        prompt = SUMMARIZE_PROMPT_TEMPLATE.format(context=context)

        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._settings.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        if not self._embedder._use_mock:
            # Chamada real a OpenAI (ou provider compativel via base_url)
            from openai import OpenAI

            base_url = self._settings.OPENAI_BASE_URL or None
            client = OpenAI(
                api_key=self._settings.OPENAI_API_KEY,
                base_url=base_url,
            )
            try:
                response = client.chat.completions.create(
                    model=self._settings.OPENAI_MODEL,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=2048,
                )
                return response.choices[0].message.content or ""
            except Exception as exc:
                logger.error("Erro ao chamar LLM para resumo: %s", exc)
                raise SummarizeError(f"Falha ao gerar resumo: {exc}") from exc
        else:
            # Fallback mock para desenvolvimento
            return self._mock_llm_response(context)

    def _mock_llm_response(self, context: str) -> str:
        """Gera resposta mock estruturada para desenvolvimento.

        Extrai informacoes do contexto para simular resumo real.

        Args:
            context: contexto montado dos chunks.

        Returns:
            JSON simulado com as 4 chaves esperadas.
        """
        # Usa primeiros trechos do contexto para simular conteudo
        first_snippet = context[:300] if context else "sem contexto disponivel"

        mock_summary = {
            "objective": f"Objetivo extraido do contexto: {first_snippet[:100]}...",
            "methodology": "Metodologia simulada baseada no contexto fornecido.",
            "results": "Resultados simulados baseados no contexto fornecido.",
            "conclusion": "Conclusao simulada baseada no contexto fornecido.",
        }
        return json.dumps(mock_summary, ensure_ascii=False)

    def _parse_response(self, raw_response: str) -> dict[str, str]:
        """Faz parsing da resposta do LLM para garantir estrutura com 4 chaves.

        Tenta extrair JSON da resposta. Se alguma chave estiver ausente,
        preenche com valor padrao 'Nao identificado'.

        Args:
            raw_response: resposta bruta do LLM.

        Returns:
            Dict com as 4 chaves: objective, methodology, results, conclusion.
        """
        summary: dict[str, str] = {
            "objective": NOT_IDENTIFIED,
            "methodology": NOT_IDENTIFIED,
            "results": NOT_IDENTIFIED,
            "conclusion": NOT_IDENTIFIED,
        }

        try:
            # Tenta extrair JSON da resposta (pode ter markdown code blocks)
            json_str = raw_response.strip()

            # Remove code blocks se presentes
            if json_str.startswith("```"):
                json_str = re.sub(r"^```(?:json)?\s*", "", json_str)
                json_str = re.sub(r"\s*```$", "", json_str)

            parsed = json.loads(json_str)

            if isinstance(parsed, dict):
                for key in SUMMARY_KEYS:
                    value = parsed.get(key)
                    if value and isinstance(value, str) and value.strip():
                        summary[key] = value.strip()

        except (json.JSONDecodeError, Exception) as exc:
            logger.warning(
                "Falha ao fazer parsing da resposta do LLM: %s. Resposta bruta: %s",
                exc,
                raw_response[:200],
            )

        return summary


class SummarizeError(Exception):
    """Erro durante geracao de resumo."""

    pass
