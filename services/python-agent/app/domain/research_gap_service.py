"""
Servico de dominio para identificacao de lacunas de pesquisa.

Responsavel por:
- Recuperar todos os chunks de um projeto do pgvector
- Opcionalmente ranquear chunks por relevancia ao tema informado
- Analisar o corpus para identificar temas cobertos vs nao cobertos
- Chamar LLM com prompt academico pedindo identificacao de lacunas
- Fazer parsing da resposta para lista de ResearchGapItem
- Calcular confidence baseado na quantidade de evidencia
- Retornar ResearchGapResponse estruturado
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.config import Settings
from app.infrastructure.database.pgvector_store import PgVectorStore
from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder
from app.schemas.contracts_v1 import (
    ResearchGapItem,
    ResearchGapResponse,
    Source,
)

logger = logging.getLogger(__name__)

# Prompt academico para identificacao de lacunas de pesquisa
RESEARCH_GAP_PROMPT_TEMPLATE = (
    "Voce e um pesquisador academico especializado em identificar lacunas de pesquisa. "
    "Com base no corpus de documentos academicos fornecido abaixo, identifique de 3 a 5 "
    "lacunas de pesquisa relevantes. Para cada lacuna, forneca:\n"
    "- gap_title: titulo conciso da lacuna (maximo 80 caracteres)\n"
    "- why_gap: explicacao detalhada do porquee esta e uma lacuna importante (2-3 frases)\n"
    "- suggested_questions: lista de 2-3 perguntas de pesquisa que poderiam abordar esta lacuna\n"
    "- evidence_sources: lista de fontes do corpus que evidenciam a existencia desta lacuna\n\n"
    "Retorne APENAS um JSON valido no seguinte formato:\n"
    '[{{"gap_title": "...", "why_gap": "...", "suggested_questions": ["...", "..."], '
    '"evidence_sources": [{{"document": "...", "page": 0, "score": 0.0}}]}}]\n\n'
    "Se o corpus estiver vazio ou insuficiente, retorne uma lista vazia: []\n\n"
    "Corpus:\n{context}"
)

# Limite maximo de chunks para analise de lacunas
MAX_CHUNKS_FOR_GAP_ANALYSIS = 30

# Numero maximo de lacunas a identificar
MAX_GAPS = 5


class ResearchGapService:
    """Orquestra fluxo de identificacao de lacunas: chunks → contexto → LLM → parsing."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedder: OpenAIEmbedder | None = None,
        vector_store: PgVectorStore | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._embedder = embedder or OpenAIEmbedder(self._settings)
        self._vector_store = vector_store or PgVectorStore(self._settings)

    def find_gaps(
        self,
        project_id: str,
        theme: str = "",
    ) -> ResearchGapResponse:
        """Identifica lacunas de pesquisa em um projeto.

        Fluxo:
        1. Recupera chunks do projeto do pgvector
        2. Se theme informado, usa embedding para ranquear chunks relevantes
        3. Monta corpus com chunks recuperados
        4. Chama LLM com prompt academico pedindo identificacao de lacunas
        5. Parsing estrito para lista de ResearchGapItem
        6. Calcula confidence baseado na quantidade de chunks
        7. Se corpus vazio, retorna gaps vazias

        Args:
            project_id: identificador do projeto para buscar chunks.
            theme: tema opcional para filtrar chunks mais relevantes.

        Returns:
            ResearchGapResponse com lista de lacunas identificadas.
        """
        logger.info(
            "Iniciando identificacao de lacunas: project_id=%s, theme=%s",
            project_id,
            theme,
        )

        # 1. Recupera chunks do projeto
        if theme:
            # Usa embedding do tema para ranquear chunks relevantes
            query_embedding = self._embedder.embed_query(theme)
            chunks = self._vector_store.search_similar_by_project(
                project_id=project_id,
                query_embedding=query_embedding,
                top_k=MAX_CHUNKS_FOR_GAP_ANALYSIS,
                min_score=0.3,  # Score mais baixo para capturar mais chunks
            )
        else:
            # Sem tema: busca generica com embedding de query vazia
            # Usa embedding de texto generico para recuperar chunks do projeto
            generic_embedding = self._embedder.embed_query("academic research document")
            chunks = self._vector_store.search_similar_by_project(
                project_id=project_id,
                query_embedding=generic_embedding,
                top_k=MAX_CHUNKS_FOR_GAP_ANALYSIS,
                min_score=0.3,
            )

        logger.info(
            "Chunks recuperados para analise de lacunas: %d",
            len(chunks),
        )

        # 2. Se corpus vazio, retorna resposta vazia
        if not chunks:
            logger.warning(
                "Corpus vazio para identificacao de lacunas: project_id=%s",
                project_id,
            )
            return ResearchGapResponse(
                project_id=UUID(project_id),
                gaps=[],
            )

        # 3. Monta contexto com chunks
        context = self._build_context(chunks)

        # 4. Chama LLM com prompt de identificacao de lacunas
        raw_response = self._call_llm(context)

        # 5. Faz parsing da resposta
        gaps = self._parse_response(raw_response, chunks)

        # 6. Calcula confidence baseado na quantidade de chunks
        confidence = self._calculate_confidence(len(chunks))

        # Aplica confidence a todas as lacunas
        for gap in gaps:
            gap.confidence = confidence

        logger.info(
            "Lacunas identificadas: %d, confidence=%s, project_id=%s",
            len(gaps),
            confidence,
            project_id,
        )

        return ResearchGapResponse(
            project_id=UUID(project_id),
            gaps=gaps,
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
        """Chama LLM com contexto para identificar lacunas de pesquisa.

        Usa OpenAI API com fallback mock para desenvolvimento.
        Temperatura 0.3 para equilibrio entre criatividade e consistencia.

        Args:
            context: contexto montado a partir dos chunks.

        Returns:
            Resposta bruta do LLM.
        """
        prompt = RESEARCH_GAP_PROMPT_TEMPLATE.format(context=context)

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
                    temperature=0.3,
                    max_tokens=2048,
                )
                return response.choices[0].message.content or ""
            except Exception as exc:
                logger.error("Erro ao chamar LLM para lacunas de pesquisa: %s", exc)
                raise ResearchGapError(f"Falha ao identificar lacunas: {exc}") from exc
        else:
            # Fallback mock para desenvolvimento
            return self._mock_llm_response(context)

    def _mock_llm_response(self, context: str) -> str:
        """Gera resposta mock estruturada para desenvolvimento.

        Extrai informacoes do contexto para simular identificacao de lacunas real.

        Args:
            context: contexto montado dos chunks.

        Returns:
            JSON simulado com lista de lacunas de pesquisa.
        """
        # Conta documentos no contexto para gerar resposta mais realista
        doc_ids = set()
        for line in context.split("\n"):
            if "Documento:" in line:
                # Extrai document_id
                match = re.search(r"Documento:\s*([^,]+)", line)
                if match:
                    doc_ids.add(match.group(1).strip())

        doc_count = len(doc_ids) if doc_ids else 1

        mock_gaps = [
            {
                "gap_title": f"Impacto de metodologias ativas no aprendizado de {doc_count} documentos analisados",
                "why_gap": (
                    "Os documentos analisados abordam metodologias tradicionais, "
                    "mas ha pouca evidencia sobre a eficacia de abordagens ativas "
                    "no contexto especifico estudado."
                ),
                "suggested_questions": [
                    "Como metodologias ativas afetam o engajamento em cursos superiores?",
                    "Qual a comparacao de resultados entre ensino tradicional e ativo?",
                ],
                "evidence_sources": [
                    {
                        "document": str(list(doc_ids)[0])
                        if doc_ids
                        else "desconhecido",
                        "page": 1,
                        "score": 0.85,
                    }
                ],
            },
            {
                "gap_title": "Integracao de tecnologias emergentes na pratica academica",
                "why_gap": (
                    "Embora os documentos mencionem tecnologia, falta investigacao "
                    "empirica sobre a integracao efetiva de IA e ferramentas digitais "
                    "no cotidiano academico."
                ),
                "suggested_questions": [
                    "Quais barreiras impedem a adocao de IA na educacao superior?",
                    "Como medir o impacto de ferramentas digitais no desempenho?",
                ],
                "evidence_sources": [
                    {
                        "document": str(list(doc_ids)[-1])
                        if doc_ids
                        else "desconhecido",
                        "page": 2,
                        "score": 0.78,
                    }
                ],
            },
        ]
        return json.dumps(mock_gaps, ensure_ascii=False)

    def _parse_response(
        self, raw_response: str, chunks: list[dict[str, Any]]
    ) -> list[ResearchGapItem]:
        """Faz parsing da resposta do LLM para lista de ResearchGapItem.

        Tenta extrair JSON da resposta. Se falhar, retorna lista vazia.
        Valida cada item e extrai fontes dos chunks disponiveis.

        Args:
            raw_response: resposta bruta do LLM.
            chunks: chunks originais para extracao de fontes.

        Returns:
            Lista de ResearchGapItem validados.
        """
        gaps: list[ResearchGapItem] = []

        try:
            # Tenta extrair JSON da resposta (pode ter markdown code blocks)
            json_str = raw_response.strip()

            # Remove code blocks se presentes
            if json_str.startswith("```"):
                json_str = re.sub(r"^```(?:json)?\s*", "", json_str)
                json_str = re.sub(r"\s*```$", "", json_str)

            parsed = json.loads(json_str)

            if not isinstance(parsed, list):
                logger.warning(
                    "Resposta do LLM nao e uma lista: tipo=%s",
                    type(parsed).__name__,
                )
                return gaps

            for item in parsed:
                if not isinstance(item, dict):
                    continue

                gap_title = item.get("gap_title", "").strip()
                why_gap = item.get("why_gap", "").strip()

                if not gap_title or not why_gap:
                    # Item incompleto — ignora
                    continue

                suggested_questions = item.get("suggested_questions", [])
                if not isinstance(suggested_questions, list):
                    suggested_questions = []

                # Extrai fontes da resposta ou usa chunks disponiveis
                evidence_sources = self._extract_sources(item, chunks)

                gaps.append(
                    ResearchGapItem(
                        gap_title=gap_title,
                        why_gap=why_gap,
                        evidence_sources=evidence_sources,
                        suggested_questions=suggested_questions[:3],  # Max 3 perguntas
                        confidence="medium",  # Sera sobrescrito pelo calculo final
                    )
                )

                # Limita numero maximo de lacunas
                if len(gaps) >= MAX_GAPS:
                    break

        except (json.JSONDecodeError, Exception) as exc:
            logger.warning(
                "Falha ao fazer parsing da resposta do LLM para lacunas: %s. "
                "Resposta bruta: %s",
                exc,
                raw_response[:200],
            )

        return gaps

    def _extract_sources(
        self, item: dict[str, Any], chunks: list[dict[str, Any]]
    ) -> list[Source]:
        """Extrai fontes estruturadas de um item de lacuna.

        Tenta usar fontes da resposta do LLM; se invalidas, usa chunks disponiveis.

        Args:
            item: item de lacuna parseado do JSON.
            chunks: chunks originais para fallback.

        Returns:
            Lista de objetos Source.
        """
        sources: list[Source] = []

        # Tenta usar fontes da resposta do LLM
        llm_sources = item.get("evidence_sources", [])
        if isinstance(llm_sources, list) and llm_sources:
            for src in llm_sources[:3]:  # Max 3 fontes por lacuna
                if isinstance(src, dict):
                    try:
                        sources.append(
                            Source(
                                document=str(src.get("document", "desconhecido")),
                                page=int(src.get("page", 0)),
                                section=src.get("section"),
                                score=float(src.get("score", 0.0)),
                            )
                        )
                    except (ValueError, TypeError):
                        continue

        # Se nao ha fontes validas da resposta, usa chunks disponiveis
        if not sources and chunks:
            for chunk in chunks[:2]:
                meta = chunk.get("metadata", {})
                sources.append(
                    Source(
                        document=str(meta.get("document_id", "desconhecido")),
                        page=int(meta.get("page_number", 0)),
                        section=meta.get("section"),
                        score=round(chunk.get("score", 0.0), 4),
                    )
                )

        return sources

    def _calculate_confidence(self, chunk_count: int) -> str:
        """Calcula nivel de confidence baseado na quantidade de chunks.

        - high: > 10 chunks no corpus
        - medium: 5-10 chunks
        - low: < 5 chunks

        Args:
            chunk_count: numero de chunks no corpus.

        Returns:
            String com nivel de confidence: "low", "medium" ou "high".
        """
        if chunk_count > 10:
            return "high"
        elif chunk_count >= 5:
            return "medium"
        else:
            return "low"


class ResearchGapError(Exception):
    """Erro durante identificacao de lacunas de pesquisa."""

    pass
