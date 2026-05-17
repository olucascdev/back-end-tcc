"""
Servico de dominio para orquestracao de RAG (Retrieval-Augmented Generation).

Responsavel por:
- Gerar embedding da pergunta do usuario
- Buscar chunks similares no pgvector filtrados por project_id
- Montar contexto a partir dos chunks recuperados
- Chamar LLM com prompt do sistema + contexto + pergunta
- Extrair fontes dos chunks usados
- Retornar resposta estruturada com citacoes
- Persistir sessao e historico no banco de dados
- Suportar modo de retrieval: project_only ou project_plus_public
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Literal

from app.core.config import Settings
from app.domain.retrieval.public_source_retriever import PublicSourceRetriever
from app.infrastructure.database import conversation_repository, session_repository
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

# Tipos de modo de retrieval
RetrievalMode = Literal["project_only", "project_plus_public"]


class RAGService:
    """Orquestra fluxo RAG: embedding → busca → contexto → LLM → resposta."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedder: OpenAIEmbedder | None = None,
        vector_store: PgVectorStore | None = None,
        public_retriever: PublicSourceRetriever | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._embedder = embedder or OpenAIEmbedder(self._settings)
        self._vector_store = vector_store or PgVectorStore(self._settings)
        self._public_retriever = public_retriever or PublicSourceRetriever(self._settings)

    @property
    def public_retrieval_enabled(self) -> bool:
        """Retorna se o modo project_plus_public esta habilitado."""
        return getattr(self._settings, "ENABLE_PUBLIC_RETRIEVAL", False)

    @property
    def _llm_available(self) -> bool:
        """Verifica se uma chave de API valida esta configurada para chamadas LLM.

        Independente do status de mock dos embeddings, o LLM pode ser
        chamado diretamente quando a chave de API esta presente e
        diferente de 'mock'.
        """
        return bool(
            self._settings.OPENAI_API_KEY
            and self._settings.OPENAI_API_KEY != "mock"
        )

    def chat(
        self,
        project_id: str,
        session_id: str,
        message: str,
        retrieval_mode: RetrievalMode = "project_only",
    ) -> ChatResponse:
        """Processa pergunta do usuario com RAG e retorna resposta com fontes.

        Fluxo:
        1. Garante sessao existente no banco
        2. Salva mensagem do usuario no historico
        3. Gera embedding da pergunta
        4. Busca chunks similares no pgvector (filtro project_id)
        5. Se retrieval_mode == "project_plus_public", busca tambem na biblioteca publica
        6. Mescla resultados, deduplica por hash de conteudo, ranqueia por score
        7. Se sem contexto relevante → retorna limitacao explicita
        8. Monta contexto + prompt do sistema
        9. Chama LLM com historico recente
        10. Extrai fontes dos chunks
        11. Persiste resposta do assistant
        12. Retorna ChatResponse

        Args:
            project_id: identificador do projeto para filtrar documentos.
            session_id: identificador da sessao de chat.
            message: pergunta do usuario.
            retrieval_mode: "project_only" (padrao) ou "project_plus_public".

        Returns:
            ChatResponse com answer, sources e session_id.
        """
        # 1. Garante sessao existente (cria se necessario)
        session_repository.get_or_create_session(
            session_id=session_id,
            project_id=project_id,
            settings=self._settings,
        )

        # 2. Salva mensagem do usuario no banco
        conversation_repository.save_message(
            session_id=session_id,
            project_id=project_id,
            role="user",
            content=message,
            settings=self._settings,
        )

        # 3. Gera embedding da pergunta
        query_embedding = self._embedder.embed_query(message)

        # 4. Busca chunks do projeto
        project_chunks = self._vector_store.search_similar_by_project(
            project_id=project_id,
            query_embedding=query_embedding,
            top_k=5,
            min_score=MIN_RELEVANCE_SCORE,
        )

        # 5. Busca chunks da biblioteca publica se modo permitir
        public_chunks: list[dict[str, Any]] = []
        if retrieval_mode == "project_plus_public":
            public_chunks = self._public_retriever.retrieve(
                query=message,
                query_embedding=query_embedding,
                top_k=5,
            )
            logger.info(
                "Retrieval project_plus_public: project=%d, public=%d chunks",
                len(project_chunks),
                len(public_chunks),
            )

        # 6. Mescla, deduplica e ranqueia
        chunks = self._merge_and_deduplicate(project_chunks, public_chunks, top_k=5)

        # 7. Sem contexto relevante → retorna limitacao
        if not chunks:
            logger.info(
                "Sem contexto relevante para project_id=%s, message=%s, mode=%s",
                project_id,
                message[:80],
                retrieval_mode,
            )
            answer = NO_CONTEXT_ANSWER

            # Persiste resposta do assistant
            conversation_repository.save_message(
                session_id=session_id,
                project_id=project_id,
                role="assistant",
                content=answer,
                sources=[],
                settings=self._settings,
            )

            return ChatResponse(
                answer=answer,
                sources=[],
                session_id=session_id,
            )

        # 8. Monta contexto a partir dos chunks
        context = self._build_context(chunks)

        # 9. Chama LLM com contexto e historico
        answer = self._call_llm(
            context=context,
            question=message,
            session_id=session_id,
        )

        # 10. Extrai fontes dos chunks
        sources = self._extract_sources(chunks)

        # 11. Persiste resposta do assistant com fontes
        sources_data = [src.model_dump() for src in sources]
        conversation_repository.save_message(
            session_id=session_id,
            project_id=project_id,
            role="assistant",
            content=answer,
            sources=sources_data,
            settings=self._settings,
        )

        logger.info(
            "RAG completo: project_id=%s, session_id=%s, mode=%s, %d fontes",
            project_id,
            session_id,
            retrieval_mode,
            len(sources),
        )

        return ChatResponse(
            answer=answer,
            sources=sources,
            session_id=session_id,
        )

    def _merge_and_deduplicate(
        self,
        project_chunks: list[dict[str, Any]],
        public_chunks: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Mescla chunks do projeto e da biblioteca publica, deduplicando por conteudo.

        Estrategia:
        1. Combina todas as listas de chunks
        2. Deduplica por hash do conteudo (evita repeticoes)
        3. Ordena por score descendente
        4. Retorna top_k resultados

        Args:
            project_chunks: chunks recuperados do projeto.
            public_chunks: chunks recuperados da biblioteca publica.
            top_k: numero maximo de resultados finais.

        Returns:
            Lista mesclada e deduplicada de chunks.
        """
        all_chunks = project_chunks + public_chunks

        # Deduplica por hash do conteudo
        seen_hashes: set[str] = set()
        unique_chunks: list[dict[str, Any]] = []
        for chunk in all_chunks:
            content_hash = hashlib.md5(chunk["content"].encode("utf-8")).hexdigest()
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                unique_chunks.append(chunk)

        # Ordena por score descendente e limita a top_k
        unique_chunks.sort(key=lambda c: c["score"], reverse=True)
        return unique_chunks[:top_k]

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
        Carrega historico recente do banco para contexto da conversa.

        Args:
            context: contexto montado a partir dos chunks.
            question: pergunta original do usuario.
            session_id: usado para carregar historico da sessao.

        Returns:
            Resposta gerada pelo LLM.
        """
        # Carrega historico recente do banco (ultimas 6 mensagens = 3 trocas)
        history = conversation_repository.get_conversation_history(
            session_id=session_id,
            limit=6,
            settings=self._settings,
        )

        # Monta mensagens para a API
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._settings.SYSTEM_PROMPT},
        ]

        # Adiciona historico recente (excluindo a ultima que e a mensagem atual do user)
        for msg in history[:-1]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Mensagem do usuario com contexto
        user_content = f"Contexto dos documentos:\n{context}\n\nPergunta: {question}"
        messages.append({"role": "user", "content": user_content})

        if self._llm_available:
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

        Para chunks da biblioteca publica (source_type='public_library'),
        define source_type='public_library'. Para demais, usa 'project_document'.

        Args:
            chunks: lista de chunks com metadata e score.

        Returns:
            Lista de objetos Source para citacao.
        """
        sources: list[Source] = []
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            chunk_source_type = meta.get("source_type", "user_upload")

            if chunk_source_type == "public_library":
                title = meta.get("title", meta.get("document_id", "desconhecido"))
                sources.append(
                    Source(
                        document=title,
                        page=0,
                        section=meta.get("section"),
                        score=round(chunk["score"], 4),
                        source_type="public_library",
                    )
                )
            else:
                sources.append(
                    Source(
                        document=str(meta.get("document_id", "desconhecido")),
                        page=int(meta.get("page_number", 0)),
                        section=meta.get("section"),
                        score=round(chunk["score"], 4),
                        source_type="project_document",
                    )
                )
        return sources


class LLMError(Exception):
    """Erro durante chamada ao LLM."""

    pass
