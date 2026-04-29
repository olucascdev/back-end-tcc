"""
Metricas academicas para avaliacao de pipeline RAG.

Implementa 4 metricas padrao da literatura:
- Faithfulness: proporcao de afirmacoes na resposta suportadas pelo contexto
- Answer Relevancy: similaridade semantica entre pergunta e resposta
- Context Precision: proporcao de chunks recuperados que sao relevantes
- Context Recall: proporcao de chunks esperados que foram recuperados

Todas as funcoes sao puras e testaveis isoladamente.
"""

from __future__ import annotations

import re
import string
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Utilitarios de texto
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> list[str]:
    """Divide texto em sentencas usando pontuacao como delimitador.

    Args:
        text: texto completo da resposta ou contexto.

    Returns:
        Lista de sentencas limpas (sem espacos extras).
    """
    # Divide por pontuacao final (. ! ?) mantendo o delimitador
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in raw if s.strip()]


def _tokenize(text: str) -> set[str]:
    """Tokeniza texto em conjunto de palavras normalizadas.

    Remove pontuacao, converte para minusculas e descarta stopwords basicas.

    Args:
        text: texto original.

    Returns:
        Conjunto de tokens normalizados.
    """
    stop_words = {
        "o",
        "a",
        "os",
        "as",
        "um",
        "uma",
        "uns",
        "umas",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "por",
        "para",
        "com",
        "sem",
        "que",
        "e",
        "ou",
        "se",
        "mas",
        "como",
        "ao",
        "aos",
        "a",
        "e",
        "nao",
        "mais",
        "muito",
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "dare",
        "ought",
        "used",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "again",
        "further",
        "then",
        "once",
        "and",
        "but",
        "or",
        "nor",
        "not",
        "so",
        "yet",
        "both",
        "either",
        "neither",
        "each",
        "every",
        "all",
        "any",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "only",
        "own",
        "same",
        "than",
        "too",
        "very",
        "just",
        "because",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "him",
        "his",
        "she",
        "her",
        "they",
        "them",
        "their",
        "what",
        "which",
        "who",
        "whom",
        "when",
        "where",
        "why",
        "how",
    }
    # Remove pontuacao e normaliza
    cleaned = text.lower().translate(str.maketrans("", "", string.punctuation))
    tokens = set(cleaned.split())
    return tokens - stop_words


# ---------------------------------------------------------------------------
# Faithfulness
# ---------------------------------------------------------------------------


def compute_faithfulness(
    answer: str,
    context_chunks: list[dict[str, Any]],
) -> float:
    """Calcula faithfulness: proporcao de afirmacoes na resposta suportadas pelo contexto.

    Heuristica:
    1. Divide resposta em sentencas (cada sentenca = uma afirmacao)
    2. Para cada sentenca, extrai tokens (palavras-chave)
    3. Verifica se algum chunk de contexto contem >= 50% dos tokens da sentenca
    4. Faithfulness = sentencas_suportadas / total_sentencas

    Se nao houver sentencas ou chunks, retorna 0.0.

    Args:
        answer: texto da resposta gerada pelo LLM.
        context_chunks: lista de chunks com chave "content".

    Returns:
        Float entre 0.0 e 1.0.
    """
    if not answer or not context_chunks:
        return 0.0

    sentences = _split_sentences(answer)
    if not sentences:
        return 0.0

    # Pre-computa tokens de todos os chunks
    chunk_tokens_list = [_tokenize(chunk["content"]) for chunk in context_chunks]

    supported_count = 0
    for sentence in sentences:
        sentence_tokens = _tokenize(sentence)
        if not sentence_tokens:
            continue

        # Verifica se algum chunk suporta esta sentenca
        is_supported = False
        for chunk_tokens in chunk_tokens_list:
            if not chunk_tokens:
                continue
            overlap = sentence_tokens & chunk_tokens
            # Suporta se >= 50% dos tokens da sentenca estao no chunk
            if len(overlap) / len(sentence_tokens) >= 0.5:
                is_supported = True
                break

        if is_supported:
            supported_count += 1

    return supported_count / len(sentences)


# ---------------------------------------------------------------------------
# Answer Relevancy
# ---------------------------------------------------------------------------


def compute_answer_relevancy(
    question_embedding: list[float],
    answer_embedding: list[float],
) -> float:
    """Calcula answer relevancy via similaridade cosseno entre embeddings.

    Usa produto escalar de vetores normalizados (cosine similarity).

    Args:
        question_embedding: embedding da pergunta.
        answer_embedding: embedding da resposta.

    Returns:
        Float entre -1.0 e 1.0 (tipicamente 0-1 para embeddings OpenAI).
    """
    q = np.array(question_embedding, dtype=np.float64)
    a = np.array(answer_embedding, dtype=np.float64)

    # Cosine similarity
    norm_q = np.linalg.norm(q)
    norm_a = np.linalg.norm(a)

    if norm_q == 0 or norm_a == 0:
        return 0.0

    return float(np.dot(q, a) / (norm_q * norm_a))


# ---------------------------------------------------------------------------
# Context Precision
# ---------------------------------------------------------------------------


def compute_context_precision(
    question: str,
    retrieved_chunks: list[dict[str, Any]],
    question_embedding: list[float] | None = None,
    chunk_embeddings: list[list[float]] | None = None,
    keyword_threshold: float = 0.3,
    embedding_threshold: float = 0.6,
) -> float:
    """Calcula context precision: proporcao de chunks recuperados que sao relevantes.

    Heuristica hibrida:
    1. Keyword overlap: chunk e relevante se contem >= keyword_threshold dos
       tokens da pergunta
    2. Embedding similarity (opcional): chunk e relevante se similaridade
       cosseno >= embedding_threshold
    3. Chunk e relevante se passar em pelo menos um dos criterios

    Se nao houver chunks recuperados, retorna 0.0.

    Args:
        question: texto da pergunta original.
        retrieved_chunks: lista de chunks recuperados com chave "content".
        question_embedding: embedding da pergunta (opcional, para criterio semantico).
        chunk_embeddings: embeddings dos chunks na mesma ordem (opcional).
        keyword_threshold: proporcao minima de tokens sobrepostos (0-1).
        embedding_threshold: similaridade cosseno minima (0-1).

    Returns:
        Float entre 0.0 e 1.0.
    """
    if not retrieved_chunks:
        return 0.0

    question_tokens = _tokenize(question)
    relevant_count = 0

    for idx, chunk in enumerate(retrieved_chunks):
        chunk_tokens = _tokenize(chunk["content"])

        # Criterio 1: keyword overlap
        keyword_relevant = False
        if question_tokens and chunk_tokens:
            overlap = question_tokens & chunk_tokens
            if len(overlap) / len(question_tokens) >= keyword_threshold:
                keyword_relevant = True

        # Criterio 2: embedding similarity (se disponivel)
        embedding_relevant = False
        if question_embedding is not None and chunk_embeddings is not None:
            if idx < len(chunk_embeddings):
                sim = compute_answer_relevancy(
                    question_embedding, chunk_embeddings[idx]
                )
                if sim >= embedding_threshold:
                    embedding_relevant = True

        # Chunk e relevante se passar em pelo menos um criterio
        if keyword_relevant or embedding_relevant:
            relevant_count += 1

    return relevant_count / len(retrieved_chunks)


# ---------------------------------------------------------------------------
# Context Recall
# ---------------------------------------------------------------------------


def compute_context_recall(
    expected_context_ids: set[str],
    retrieved_context_ids: set[str],
) -> float:
    """Calcula context recall: proporcao de chunks esperados que foram recuperados.

    Recall = |esperados & recuperados| / |esperados|

    Se nao houver chunks esperados, retorna 1.0 (nada a recuperar).

    Args:
        expected_context_ids: IDs dos chunks esperados (golden dataset).
        retrieved_context_ids: IDs dos chunks efetivamente recuperados.

    Returns:
        Float entre 0.0 e 1.0.
    """
    if not expected_context_ids:
        return 1.0

    matched = expected_context_ids & retrieved_context_ids
    return len(matched) / len(expected_context_ids)
