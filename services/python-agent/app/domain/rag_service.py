"""
Servico de dominio para orquestracao de RAG (Retrieval-Augmented Generation).

Responsavel por:
- Gerar embedding da pergunta do usuario
- Buscar chunks similares no pgvector filtrados por project_id
- Montar contexto a partir dos chunks recuperados
- Chamar LLM com prompt do sistema + contexto + pergunta
- Extrair fontes dos chunks usados
- Retornar resposta estruturada com citacoes
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.infrastructure.database.pgvector_store import PgVectorStore
from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder
from app.schemas.contracts_v1 import ChatResponse, Source

logger = logging.getLogger(__name__)

# Threshold abaixo do qual consideramos contexto irrelevante
MIN_RELEVANCE_SCORE = 0.7

# Mensagem retornada quando nao ha contexto suficiente
NO_CONTEXT_ANSWER = (
    "Nao encontrei informacoes suficientes nos documentos do projeto para "
    "responder sua pergunta. Tente reformular ou consulte documentos diferentes."
)


class SessionHistory:
    """Armazena historico de mensagens por sessao em memoria.

    Em producao, substituir por Redis ou banco de dados.
    """

    def __init__(self) -> None:
        # session_id -> lista de mensagens {role, content}
        self._store: dict[str, list[dict[str, str]]] = {}

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Adiciona mensagem ao historico da sessao."""
        if session_id not in self._store:
            self._store[session_id] = []
        self._store[session_id].append({"role": role, "content": content})

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        """Retorna historico completo da sessao."""
        return self._store.get(session_id, [])

    def clear(self, session_id: str) -> None:
        """Limpa historico de uma sessao."""
        self._store.pop(session_id, None)


class RAGService:
    """Orquestra fluxo RAG: embedding → busca → contexto → LLM → resposta."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedder: OpenAIEmbedder | None = None,
        vector_store: PgVectorStore | None = None,
        session_history: SessionHistory | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._embedder = embedder or OpenAIEmbedder(self._settings)
        self._vector_store = vector_store or PgVectorStore(self._settings)
        self._session_history = session_history or SessionHistory()

    def chat(
        self,
        project_id: str,
        session_id: str,
        message: str,
    ) -> ChatResponse:
        """Processa pergunta do usuario com RAG e retorna resposta com fontes.

        Fluxo:
        1. Gera embedding da pergunta
        2. Busca chunks similares no pgvector (filtro project_id)
        3. Se sem contexto relevante → retorna limitacao explicita
        4. Monta contexto + prompt do sistema
        5. Chama LLM
        6. Extrai fontes dos chunks
        7. Retorna ChatResponse

        Args:
            project_id: identificador do projeto para filtrar documentos.
            session_id: identificador da sessao de chat.
            message: pergunta do usuario.

        Returns:
            ChatResponse com answer, sources e session_id.
        """
        # Salva mensagem do usuario no historico
        self._session_history.add_message(session_id, "user", message)

        # 1. Gera embedding da pergunta
        query_embedding = self._embedder.embed_query(message)

        # 2. Busca chunks similares
        chunks = self._vector_store.search_similar_by_project(
            project_id=project_id,
            query_embedding=query_embedding,
            top_k=5,
            min_score=MIN_RELEVANCE_SCORE,
        )

        # 3. Sem contexto relevante → retorna limitacao
        if not chunks:
            logger.info(
                "Sem contexto relevante para project_id=%s, message=%s",
                project_id,
                message[:80],
            )
            answer = NO_CONTEXT_ANSWER
            self._session_history.add_message(session_id, "assistant", answer)
            return ChatResponse(
                answer=answer,
                sources=[],
                session_id=session_id,
            )

        # 4. Monta contexto a partir dos chunks
        context = self._build_context(chunks)

        # 5. Monta prompt e chama LLM
        answer = self._call_llm(
            context=context, question=message, session_id=session_id
        )

        # 6. Extrai fontes dos chunks
        sources = self._extract_sources(chunks)

        # Salva resposta no historico
        self._session_history.add_message(session_id, "assistant", answer)

        logger.info(
            "RAG completo: project_id=%s, session_id=%s, %d fontes",
            project_id,
            session_id,
            len(sources),
        )

        return ChatResponse(
            answer=answer,
            sources=sources,
            session_id=session_id,
        )

    def _build_context(self, chunks: list[dict[str, Any]]) -> str:
        """Monta bloco de contexto a partir dos chunks recuperados.

        Cada chunk e formatado com conteudo e metadados para o LLM
        entender a origem da informacao.

        Args:
            chunks: lista de chunks com content, metadata e score.

        Returns:
            String formatada com contexto para o prompt.
        """
        parts: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            meta = chunk.get("metadata", {})
            doc_name = meta.get("document_id", "desconhecido")
            page = meta.get("page_number", "?")
            parts.append(
                f"[Fonte {idx}] Documento: {doc_name}, Pagina: {page}\n"
                f"Conteudo: {chunk['content']}"
            )
        return "\n\n".join(parts)

    def _call_llm(
        self,
        context: str,
        question: str,
        session_id: str,
    ) -> str:
        """Chama LLM com contexto + pergunta e retorna resposta.

        Usa OpenAI API com fallback mock para desenvolvimento.

        Args:
            context: contexto montado a partir dos chunks.
            question: pergunta original do usuario.
            session_id: usado para incluir historico da sessao.

        Returns:
            Resposta gerada pelo LLM.
        """
        # Monta historico da sessao para contexto adicional
        history = self._session_history.get_history(session_id)
        # Usa apenas as ultimas 6 mensagens (3 trocas) para nao estourar tokens
        recent_history = history[-6:] if len(history) > 6 else history

        # Monta mensagens para a API
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._settings.SYSTEM_PROMPT},
        ]

        # Adiciona historico recente (excluindo a mensagem atual que ja foi salva)
        for msg in recent_history[:-1]:  # ultima e a mensagem atual do user
            messages.append(msg)

        # Mensagem do usuario com contexto
        user_content = f"Contexto dos documentos:\n{context}\n\nPergunta: {question}"
        messages.append({"role": "user", "content": user_content})

        if not self._embedder._use_mock:
            # Chamada real a OpenAI
            from openai import OpenAI

            client = OpenAI(api_key=self._settings.OPENAI_API_KEY)
            try:
                response = client.chat.completions.create(
                    model=self._settings.OPENAI_MODEL,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=1024,
                )
                return response.choices[0].message.content or ""
            except Exception as exc:
                logger.error("Erro ao chamar LLM: %s", exc)
                raise LLMError(f"Falha ao gerar resposta: {exc}") from exc
        else:
            # Fallback mock para desenvolvimento
            return self._mock_llm_response(context, question)

    def _mock_llm_response(self, context: str, question: str) -> str:
        """Gera resposta mock baseada no contexto para desenvolvimento.

        Simula comportamento do LLM usando informacoes do contexto.

        Args:
            context: contexto montado dos chunks.
            question: pergunta do usuario.

        Returns:
            Resposta simulada.
        """
        # Extrai primeiras palavras do contexto para simular resposta
        first_chunk = context.split("\n\n")[0] if context else ""
        snippet = first_chunk[:200] if first_chunk else "sem contexto"

        return (
            f"Com base nos documentos fornecidos:\n\n{snippet}\n\n"
            f"Esta e uma resposta simulada (modo mock). "
            f"Configure OPENAI_API_KEY para respostas reais."
        )

    def _extract_sources(self, chunks: list[dict[str, Any]]) -> list[Source]:
        """Extrai fontes estruturadas a partir dos chunks recuperados.

        Args:
            chunks: lista de chunks com metadata e score.

        Returns:
            Lista de objetos Source para citacao.
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
        return sources


class LLMError(Exception):
    """Erro durante chamada ao LLM."""

    pass
