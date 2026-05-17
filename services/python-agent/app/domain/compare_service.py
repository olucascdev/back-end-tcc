"""
Servico de dominio para comparacao tematica entre documentos academicos.

Responsavel por:
- Gerar embedding do tema de comparacao
- Buscar chunks similares no pgvector filtrados por project_id
- Filtrar chunks pelos document_ids informados
- Agrupar chunks por document_id
- Montar contexto estruturado por documento
- Chamar LLM com prompt academico para comparacao tematica
- Fazer parsing da resposta para garantir estrutura com 3 chaves
- Extrair fontes rastreaveis dos chunks usados
- Retornar CompareResponse estruturado
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import Settings
from app.infrastructure.database.pgvector_store import PgVectorStore
from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder
from app.schemas.contracts_v1 import CompareResponse, Source

logger = logging.getLogger(__name__)

# Chaves esperadas na comparacao estruturada
COMPARISON_KEYS = ["similarities", "differences", "synthesis"]

# Mensagem padrao quando nao ha contexto suficiente
INSUFFICIENT_CONTEXT = "Contexto insuficiente para comparacao tematica."

# Prompt academico deterministico para geracao de comparacao tematica
COMPARE_PROMPT_TEMPLATE = (
    "Voce e um assistente especializado em analisar e comparar documentos academicos. "
    "Com base no contexto fornecido abaixo, que contem trechos de diferentes documentos "
    "relacionados ao tema '{theme}', faca uma comparacao tematica estruturada contendo "
    "exatamente as seguintes tres secoes:\n"
    "- similarities: pontos em comum entre os documentos sobre o tema\n"
    "- differences: divergencias ou abordagens distintas entre os documentos\n"
    "- synthesis: sintese geral da comparacao tematica\n\n"
    "Retorne APENAS um JSON valido com essas tres chaves, sem texto adicional. "
    "Exemplo de formato:\n"
    '{{"similarities": "...", "differences": "...", "synthesis": "..."}}\n\n'
    "Contexto:\n{context}"
)

# Numero maximo de chunks a buscar por tema
DEFAULT_TOP_K = 15

# Numero minimo de documentos com chunks para comparacao valida
MIN_DOCUMENTS_FOR_COMPARISON = 2


class CompareService:
    """Orquestra fluxo de comparacao tematica: embedding → busca → agrupamento → LLM → parsing."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedder: OpenAIEmbedder | None = None,
        vector_store: PgVectorStore | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._embedder = embedder or OpenAIEmbedder(self._settings)
        self._vector_store = vector_store or PgVectorStore(self._settings)

    def compare(
        self,
        project_id: str,
        document_ids: list[str],
        theme: str,
    ) -> CompareResponse:
        """Gera comparacao tematica entre documentos especificos dentro de um projeto.

        Fluxo:
        1. Gera embedding do tema
        2. Busca chunks similares no pgvector filtrando por project_id (top_k=15)
        3. Filtra chunks cujo document_id esta em document_ids
        4. Agrupa chunks por document_id
        5. Monta contexto com chunks de cada documento, separados por blocos claros
        6. Chama LLM com prompt academico pedindo comparacao estruturada
        7. Faz parsing da resposta. Se LLM nao retornar JSON valido, usa regex/heuristica
        8. Extrai fontes (Source) dos chunks usados
        9. Se nao houver chunks suficientes (< 2 docs com chunks), retorna fallback

        Args:
            project_id: identificador do projeto para filtrar documentos.
            document_ids: lista de identificadores dos documentos a comparar.
            theme: tema da comparacao.

        Returns:
            CompareResponse com comparison contendo similarities, differences,
            synthesis e sources rastreaveis.
        """
        logger.info(
            "Iniciando comparacao tematica: project_id=%s, document_ids=%s, theme=%s",
            project_id,
            document_ids,
            theme,
        )

        # 1. Gera embedding do tema
        query_embedding = self._embedder.embed_query(theme)

        # 2. Busca chunks similares no pgvector
        chunks = self._vector_store.search_similar_by_project(
            project_id=project_id,
            query_embedding=query_embedding,
            top_k=DEFAULT_TOP_K,
            min_score=0.5,
        )

        # 3. Filtra chunks pelos document_ids informados
        filtered_chunks = [
            chunk
            for chunk in chunks
            if chunk.get("metadata", {}).get("document_id") in document_ids
        ]

        logger.info(
            "Chunks recuperados: %d total, %d filtrados por document_ids",
            len(chunks),
            len(filtered_chunks),
        )

        # 4. Agrupa chunks por document_id
        chunks_by_doc = self._group_chunks_by_document(filtered_chunks)

        # 5. Verifica se ha chunks suficientes para comparacao
        if len(chunks_by_doc) < MIN_DOCUMENTS_FOR_COMPARISON:
            logger.warning(
                "Contexto insuficiente para comparacao: %d documentos com chunks "
                "(minimo: %d), project_id=%s",
                len(chunks_by_doc),
                MIN_DOCUMENTS_FOR_COMPARISON,
                project_id,
            )
            return CompareResponse(
                project_id=project_id,
                comparison={
                    "theme": theme,
                    "similarities": INSUFFICIENT_CONTEXT,
                    "differences": INSUFFICIENT_CONTEXT,
                    "synthesis": INSUFFICIENT_CONTEXT,
                },
                sources=[],
            )

        # 6. Monta contexto com chunks agrupados por documento
        context = self._build_context(chunks_by_doc)

        # 7. Chama LLM com prompt de comparacao
        raw_response = self._call_llm(context=context, theme=theme)

        # 8. Faz parsing da resposta para garantir estrutura
        comparison = self._parse_response(raw_response, theme=theme)

        # 9. Extrai fontes dos chunks usados
        sources = self._extract_sources(filtered_chunks)

        logger.info(
            "Comparacao tematica gerada com sucesso: project_id=%s, theme=%s, %d fontes",
            project_id,
            theme,
            len(sources),
        )

        return CompareResponse(
            project_id=project_id,
            comparison=comparison,
            sources=sources,
        )

    def _group_chunks_by_document(
        self, chunks: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Agrupa chunks por document_id.

        Args:
            chunks: lista de chunks com metadata contendo document_id.

        Returns:
            Dict mapeando document_id → lista de chunks desse documento.
        """
        grouped: dict[str, list[dict[str, Any]]] = {}
        for chunk in chunks:
            doc_id = chunk.get("metadata", {}).get("document_id", "desconhecido")
            if doc_id not in grouped:
                grouped[doc_id] = []
            grouped[doc_id].append(chunk)
        return grouped

    def _build_context(self, chunks_by_doc: dict[str, list[dict[str, Any]]]) -> str:
        """Monta bloco de contexto a partir dos chunks agrupados por documento.

        Cada documento recebe um bloco claro com seus chunks formatados.
        Aplica limite de tokens para evitar exceder contexto do LLM.
        Aproximacao: 1 token ~ 4 caracteres.

        Args:
            chunks_by_doc: dict mapeando document_id → lista de chunks.

        Returns:
            String formatada com contexto separado por documento para o prompt.
        """
        max_chars = self._settings.MAX_CONTEXT_TOKENS * 4
        parts: list[str] = []
        total_chars = 0

        for doc_id, doc_chunks in chunks_by_doc.items():
            doc_header = f"=== DOCUMENTO: {doc_id} ==="
            doc_parts: list[str] = [doc_header]

            for idx, chunk in enumerate(doc_chunks, start=1):
                meta = chunk.get("metadata", {})
                page = meta.get("page_number", "?")
                chunk_text = (
                    f"  [Trecho {idx}] Pagina: {page}\n  Conteudo: {chunk['content']}"
                )
                doc_parts.append(chunk_text)

            doc_block = "\n".join(doc_parts)

            # Verifica se adicionar este bloco ultrapassa o limite
            if total_chars + len(doc_block) > max_chars and parts:
                logger.debug(
                    "Limite de contexto atingido (%d chars), %d blocos incluidos",
                    max_chars,
                    len(parts),
                )
                break

            parts.append(doc_block)
            total_chars += len(doc_block)

        return "\n\n".join(parts)

    def _call_llm(self, context: str, theme: str) -> str:
        """Chama LLM com contexto e tema para gerar comparacao.

        Usa OpenAI API com fallback mock para desenvolvimento.
        Temperatura 0.2 para respostas deterministicas.

        Args:
            context: contexto montado a partir dos chunks agrupados.
            theme: tema da comparacao.

        Returns:
            Resposta bruta do LLM.
        """
        prompt = COMPARE_PROMPT_TEMPLATE.format(context=context, theme=theme)

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
                logger.error("Erro ao chamar LLM para comparacao: %s", exc)
                raise CompareError(f"Falha ao gerar comparacao: {exc}") from exc
        else:
            # Fallback mock para desenvolvimento
            return self._mock_llm_response(context, theme)

    def _mock_llm_response(self, context: str, theme: str) -> str:
        """Gera resposta mock estruturada para desenvolvimento.

        Extrai informacoes do contexto para simular comparacao real.

        Args:
            context: contexto montado dos chunks agrupados por documento.
            theme: tema da comparacao.

        Returns:
            JSON simulado com as 3 chaves esperadas.
        """
        # Conta documentos no contexto para gerar resposta mais realista
        doc_count = context.count("=== DOCUMENTO:")

        mock_comparison = {
            "similarities": (
                f"Os {doc_count} documentos compartilham abordagens sobre '{theme}'. "
                "Ha convergencia nos conceitos fundamentais e nas referencias teoricas."
            ),
            "differences": (
                "Os documentos divergem na metodologia aplicada e nos resultados empiricos. "
                "Cada autor adota perspectiva distinta sobre o tema."
            ),
            "synthesis": (
                f"A comparacao tematica sobre '{theme}' revela complementaridade entre "
                "os documentos analisados. As semelhancas indicam consenso teorico, "
                "enquanto as diferencas apontam para diversidade metodologica."
            ),
        }
        return json.dumps(mock_comparison, ensure_ascii=False)

    def _parse_response(self, raw_response: str, theme: str) -> dict[str, str]:
        """Faz parsing da resposta do LLM para garantir estrutura com 3 chaves.

        Tenta extrair JSON da resposta. Se alguma chave estiver ausente,
        preenche com valor padrao. Se JSON falhar, usa regex/heuristica
        para extrair secoes por padroes de texto.

        Args:
            raw_response: resposta bruta do LLM.
            theme: tema da comparacao (usado como fallback).

        Returns:
            Dict com as 3 chaves: similarities, differences, synthesis.
        """
        comparison: dict[str, str] = {
            "theme": theme,
            "similarities": "Nao identificado",
            "differences": "Nao identificado",
            "synthesis": "Nao identificado",
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
                for key in COMPARISON_KEYS:
                    value = parsed.get(key)
                    if value and isinstance(value, str) and value.strip():
                        comparison[key] = value.strip()

                return comparison

        except (json.JSONDecodeError, Exception) as exc:
            logger.warning(
                "Falha ao fazer parsing JSON da resposta do LLM: %s. "
                "Tentando heuristica por regex.",
                exc,
            )

        # Fallback: tenta extrair secoes por regex/heuristica
        heuristic_result = self._parse_by_heuristics(raw_response)
        for key in COMPARISON_KEYS:
            if heuristic_result.get(key):
                comparison[key] = heuristic_result[key]

        return comparison

    def _parse_by_heuristics(self, raw_response: str) -> dict[str, str]:
        """Tenta extrair secoes da resposta usando regex quando JSON falha.

        Procura por padroes como 'similarities:', 'differences:', 'synthesis:'
        ou variacoes em portugues.

        Args:
            raw_response: resposta bruta do LLM.

        Returns:
            Dict com chaves encontradas via heuristica.
        """
        result: dict[str, str] = {}

        # Padroes de regex para cada secao (ingles e portugues)
        patterns = {
            "similarities": [
                r"(?:similarities|similaridades|pontos em comum)[:\s]*(.*?)(?=differences|divergencias|synthesis|sintese|$)",
            ],
            "differences": [
                r"(?:differences|divergencias|diferencas)[:\s]*(.*?)(?=synthesis|sintese|similarities|similaridades|$)",
            ],
            "synthesis": [
                r"(?:synthesis|sintese|conclusao)[:\s]*(.*?)(?=similarities|similaridades|differences|divergencias|$)",
            ],
        }

        for key, regex_list in patterns.items():
            for pattern in regex_list:
                match = re.search(pattern, raw_response, re.IGNORECASE | re.DOTALL)
                if match:
                    extracted = match.group(1).strip()
                    if extracted:
                        result[key] = extracted
                        break

        return result

    def _extract_sources(self, chunks: list[dict[str, Any]]) -> list[Source]:
        """Extrai fontes estruturadas a partir dos chunks usados na comparacao.

        Args:
            chunks: lista de chunks com metadata e score.

        Returns:
            Lista de objetos Source para citacao, ordenados por score descendente.
        """
        sources: list[Source] = []
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            sources.append(
                Source(
                    document=str(meta.get("document_id", "desconhecido")),
                    page=int(meta.get("page_number", 0)),
                    section=meta.get("section"),
                    score=round(chunk["score"], 4),
                )
            )
        # Ordena por score descendente para priorizar fontes mais relevantes
        sources.sort(key=lambda s: s.score, reverse=True)
        return sources


class CompareError(Exception):
    """Erro durante geracao de comparacao tematica."""

    pass
