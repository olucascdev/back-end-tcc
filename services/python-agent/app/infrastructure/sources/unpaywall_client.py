"""
Cliente assincrono para a API Unpaywall.

Permite localizar URLs de PDF em acesso aberto a partir de um DOI,
utilizando o servico Unpaywall para identificar repositorios institucionais
e preprints com texto completo disponivel.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

UNPAYWALL_BASE_URL = "https://api.unpaywall.org/v2"


async def find_pdf_by_doi(doi: str, email: str) -> str | None:
    """Localiza a URL de PDF em acesso aberto para um DOI informado.

    Consulta a API Unpaywall para encontrar a melhor localizacao de acesso
    aberto (best_oa_location) associada ao DOI. Retorna a URL direta do PDF
    quando disponivel, ou a URL generica do repositorio como fallback.

    Args:
        doi: Identificador DOI do trabalho (ex: "10.1234/example.2024.001").
        email: Email de contato (obrigatorio pela politica do Unpaywall).

    Returns:
        URL do PDF em acesso aberto ou None se nao encontrado / erro.
    """
    # Normaliza o DOI removendo o prefixo "https://doi.org/" se presente
    clean_doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")

    url = f"{UNPAYWALL_BASE_URL}/{clean_doi}"
    params = {"email": email}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        best_location = data.get("best_oa_location")
        if not best_location:
            logger.info(
                "Unpaywall nao encontrou localizacao OA para DOI '%s'.",
                clean_doi,
            )
            return None

        # Prioriza URL direta do PDF; fallback para URL generica
        pdf_url = best_location.get("url_for_pdf")
        if pdf_url:
            return pdf_url

        generic_url = best_location.get("url")
        if generic_url:
            logger.info(
                "Unpaywall retornou URL generica (sem PDF direto) para DOI '%s': %s",
                clean_doi,
                generic_url,
            )
            return generic_url

        return None

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Unpaywall API retornou erro HTTP %s para DOI '%s': %s",
            exc.response.status_code,
            clean_doi,
            exc.response.text[:200],
        )
        return None

    except httpx.RequestError as exc:
        logger.warning(
            "Falha na requisicao ao Unpaywall para DOI '%s': %s",
            clean_doi,
            exc,
        )
        return None

    except Exception as exc:
        logger.warning(
            "Erro inesperado ao consultar Unpaywall para DOI '%s': %s",
            clean_doi,
            exc,
        )
        return None
