"""
Recuperador de fontes publicas on-demand com cadeia de fallback.

Orquestra a busca em OpenAlex → Unpaywall → Google Books para obter
conteudo textual relevante quando a biblioteca publica do pgvector nao
possui resultados suficientes.

Fluxo:
1. Busca trabalhos academicos no OpenAlex
2. Para cada trabalho, tenta obter texto completo:
   a. Se tiver oa_url, baixa o texto
   b. Se nao tiver oa_url mas tiver DOI, consulta Unpaywall
   c. Se ainda nao tiver, consulta Google Books como fallback
3. Aplica chunking nos textos obtidos
4. Gera embeddings dos chunks
5. Calcula similaridade com a query
6. Retorna os chunks mais relevantes
"""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app.core.config import Settings
from app.infrastructure.chunking.chunker import TextChunker
from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder
from app.infrastructure.sources.google_books_client import search_books
from app.infrastructure.sources.openalex_client import search_works
from app.infrastructure.sources.unpaywall_client import find_pdf_by_doi

logger = logging.getLogger(__name__)

# Constantes de chunking
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Limites de resultados
MAX_OPENALEX_WORKS = 5
MAX_CHUNKS_PER_WORK = 3
MAX_TOTAL_CHUNKS = 5


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calcula similaridade por produto escalar (embeddings ja normalizados).

    Como os embeddings da OpenAI sao normalizados (vetores unitarios),
    o produto escalar equivale a cosine similarity.

    Args:
        a: embedding da query.
        b: embedding do chunk.

    Returns:
        Score de similaridade entre 0 e 1.
    """
    dot = sum(x * y for x, y in zip(a, b))
    # Garante que o score fique no intervalo [0, 1]
    return max(0.0, min(1.0, dot))


def _extract_text_from_html(html: str) -> str:
    """Extrai texto legivel de HTML usando regex simples.

    Remove tags HTML, scripts, estilos e normaliza espacos.

    Args:
        html: conteudo HTML bruto.

    Returns:
        Texto extraido e limpo.
    """
    # Remove blocos de script e style
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove todas as tags HTML
    text = re.sub(r"<[^>]+>", " ", text)
    # Decodifica entidades HTML comuns
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    # Normaliza espacos em branco
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _download_text(url: str) -> str | None:
    """Baixa conteudo textual de uma URL.

    Usa httpx.Client sincrono para compatibilidade com o metodo sync
    do retriever.

    Args:
        url: URL do conteudo a ser baixado.

    Returns:
        Texto extraido ou None se falhar.
    """
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()

            # PDF: pula por enquanto (extracao de PDF e complexa)
            if "application/pdf" in content_type:
                logger.info(
                    "URL e PDF (%s); extracao de PDF nao suportada, pulando.",
                    url[:100],
                )
                return None

            # HTML: extrai texto
            if "text/html" in content_type:
                return _extract_text_from_html(response.text)

            # Texto puro ou outro tipo: tenta usar como texto
            return response.text

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Erro HTTP ao baixar texto de '%s': %s",
            url[:100],
            exc.response.status_code,
        )
        return None

    except httpx.RequestError as exc:
        logger.warning(
            "Falha na requisicao ao baixar '%s': %s",
            url[:100],
            exc,
        )
        return None

    except Exception as exc:
        logger.warning(
            "Erro inesperado ao baixar texto de '%s': %s",
            url[:100],
            exc,
        )
        return None


class PublicSourceRetriever:
    """Orquestra busca on-demand em fontes publicas com fallback chain."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._chunker = TextChunker()
        self._embedder = OpenAIEmbedder(self._settings)
        # Os clientes de fonte sao funcoes de modulo, nao precisam de instancia

    def retrieve(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """Busca fontes publicas on-demand e retorna chunks com score.

        Fluxo:
        1. Busca no OpenAlex por query (top 5 works)
        2. Para cada work, tenta obter texto:
           a. Se tiver oa_url, baixa o texto
           b. Se nao tiver oa_url mas tiver DOI, consulta Unpaywall
           c. Se ainda nao tiver, consulta Google Books
        3. Para cada texto obtido, aplica chunking
        4. Gera embeddings dos chunks
        5. Calcula cosine similarity com query_embedding
        6. Retorna top_k chunks mais similares

        Args:
            query: texto da busca do usuario.
            query_embedding: embedding da query para calculo de similaridade.
            top_k: numero maximo de chunks a retornar.

        Returns:
            Lista de chunks ordenados por score decrescente.
        """
        all_chunks: list[dict] = []

        # 1. Busca trabalhos no OpenAlex (chamada async via asyncio.run)
        works = asyncio.run(search_works(query, limit=MAX_OPENALEX_WORKS))
        logger.info(
            "PublicSourceRetriever: OpenAlex retornou %d trabalhos para query '%s'",
            len(works),
            query[:80],
        )

        # 2. Para cada work, tenta obter texto
        for work in works:
            if len(all_chunks) >= MAX_TOTAL_CHUNKS:
                break

            work_id = work.get("id", "")
            title = work.get("title", "Sem titulo")
            authors = ", ".join(work.get("authors", [])) or "Desconhecido"
            oa_url = work.get("oa_url")
            doi = work.get("doi")

            text = self._fetch_work_text(work_id, title, oa_url, doi)

            if text:
                # 3. Aplica chunking
                work_chunks = self._chunker.chunk_text(
                    text=text,
                    chunk_size=CHUNK_SIZE,
                    overlap=CHUNK_OVERLAP,
                    page_number=1,
                )

                # Limita chunks por trabalho
                work_chunks = work_chunks[:MAX_CHUNKS_PER_WORK]

                if work_chunks:
                    # 4. Gera embeddings dos chunks
                    chunk_texts = [c["text"] for c in work_chunks]
                    try:
                        chunk_embeddings = self._embedder.embed_texts(chunk_texts)
                    except Exception as exc:
                        logger.warning(
                            "Falha ao gerar embeddings para work '%s': %s",
                            work_id,
                            exc,
                        )
                        continue

                    # 5. Calcula similaridade e monta resultado
                    for chunk, embedding in zip(work_chunks, chunk_embeddings):
                        score = _cosine_similarity(query_embedding, embedding)
                        all_chunks.append(
                            {
                                "content": chunk["text"],
                                "score": score,
                                "metadata": {
                                    "document_id": work_id,
                                    "page_number": chunk.get("page_number", 1),
                                    "source_type": "public_library",
                                    "title": title,
                                    "section": f"Autores: {authors}",
                                },
                            }
                        )

        # 3. Se OpenAlex nao retornou chunks, tenta Google Books como fallback
        if not all_chunks:
            logger.info(
                "PublicSourceRetriever: OpenAlex nao retornou chunks, "
                "tentando Google Books como fallback."
            )
            all_chunks = self._retrieve_from_google_books(
                query=query,
                query_embedding=query_embedding,
                top_k=top_k,
            )

        # 6. Ordena por score e retorna top_k
        all_chunks.sort(key=lambda c: c["score"], reverse=True)
        return all_chunks[:top_k]

    def _fetch_work_text(
        self,
        work_id: str,
        title: str,
        oa_url: str | None,
        doi: str | None,
    ) -> str | None:
        """Tenta obter texto completo de um trabalho academico.

        Ordem de tentativa:
        1. oa_url direta
        2. Unpaywall via DOI
        3. Google Books (fallback)

        Args:
            work_id: identificador do trabalho.
            title: titulo do trabalho.
            oa_url: URL de acesso aberto (se disponivel).
            doi: DOI do trabalho (se disponivel).

        Returns:
            Texto extraido ou None se todas as tentativas falharem.
        """
        # Tenta oa_url direta
        if oa_url:
            logger.info(
                "Tentando baixar texto de oa_url para work '%s'",
                work_id[:60],
            )
            text = _download_text(oa_url)
            if text and len(text) > 100:
                return text

        # Tenta Unpaywall via DOI
        if doi:
            logger.info(
                "Consultando Unpaywall para DOI '%s' (work '%s')",
                doi,
                work_id[:60],
            )
            pdf_url = asyncio.run(find_pdf_by_doi(doi, self._settings.UNPAYWALL_EMAIL))
            if pdf_url:
                text = _download_text(pdf_url)
                if text and len(text) > 100:
                    return text

        # Fallback: Google Books
        logger.info(
            "Tentando Google Books como fallback para work '%s'",
            work_id[:60],
        )
        books = asyncio.run(
            search_books(
                title,
                limit=1,
                api_key=self._settings.GOOGLE_BOOKS_API_KEY,
            )
        )
        if books:
            book = books[0]
            description = book.get("description", "")
            if description:
                return description

        return None

    def _retrieve_from_google_books(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int,
    ) -> list[dict]:
        """Busca chunks via Google Books como fallback final.

        Usa o campo 'description' dos livros como texto, sem download.

        Args:
            query: texto da busca.
            query_embedding: embedding da query.
            top_k: numero maximo de chunks.

        Returns:
            Lista de chunks do Google Books.
        """
        chunks: list[dict] = []

        books = asyncio.run(
            search_books(
                query,
                limit=3,
                api_key=self._settings.GOOGLE_BOOKS_API_KEY,
            )
        )

        if not books:
            logger.info("Google Books nao retornou resultados para query '%s'", query[:80])
            return chunks

        # Coleta descricoes para gerar embeddings em batch
        descriptions: list[tuple[dict, str]] = []
        for book in books:
            desc = book.get("description", "")
            if desc:
                descriptions.append((book, desc))

        if not descriptions:
            return chunks

        # Gera embeddings em batch
        desc_texts = [d[1] for d in descriptions]
        try:
            desc_embeddings = self._embedder.embed_texts(desc_texts)
        except Exception as exc:
            logger.warning("Falha ao gerar embeddings do Google Books: %s", exc)
            return chunks

        # Calcula similaridade e monta chunks
        for (book, desc), embedding in zip(descriptions, desc_embeddings):
            score = _cosine_similarity(query_embedding, embedding)
            book_id = book.get("id", "")
            book_title = book.get("title", "Sem titulo")
            book_authors = ", ".join(book.get("authors", [])) or "Desconhecido"

            chunks.append(
                {
                    "content": desc,
                    "score": score,
                    "metadata": {
                        "document_id": book_id,
                        "page_number": 1,
                        "source_type": "public_library",
                        "title": book_title,
                        "section": f"Autores: {book_authors}",
                    },
                }
            )

        logger.info(
            "Google Books retornou %d chunks para query '%s'",
            len(chunks),
            query[:80],
        )
        return chunks
