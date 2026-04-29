"""
Servico de armazenamento de artefatos (download e MinIO).

Responsavel por selecionar formato, baixar conteudo,
computar checksum e armazenar/recuperar do MinIO.
"""

from __future__ import annotations

import hashlib
import io
import logging
from typing import Optional

import httpx
from minio import Minio

from app.core.config import Settings

logger = logging.getLogger(__name__)


class ArtifactStorageService:
    """
    Servico para download e armazenamento de artefatos de livros.

    Suporta selecao de formato por prioridade, download com retry,
    checksum SHA-256 e upload/download do MinIO.
    """

    def __init__(self, settings: Settings, minio_client: Minio) -> None:
        self._settings = settings
        self._minio = minio_client
        self._bucket = settings.MINIO_BUCKET
        self._format_priority = [
            fmt.strip()
            for fmt in settings.ARTIFACT_FORMAT_PRIORITY.split(",")
            if fmt.strip()
        ]
        self._download_timeout = httpx.Timeout(
            connect=10.0,
            read=settings.DOWNLOAD_TIMEOUT,
            write=10.0,
            pool=10.0,
        )

    def select_format(self, available_formats: list[str]) -> Optional[str]:
        """
        Seleciona melhor formato baseado na prioridade configurada.

        Prioridade padrao: txt > epub > pdf.

        Args:
            available_formats: lista de formatos disponiveis.

        Returns:
            Formato selecionado ou None se nenhum disponivel.
        """
        available_lower = {f.lower() for f in available_formats}
        for fmt in self._format_priority:
            if fmt.lower() in available_lower:
                return fmt.lower()
        return None

    async def download_artifact(self, url: str) -> bytes:
        """
        Baixa artefato de URL com retry e timeout.

        Args:
            url: URL do artefato.

        Returns:
            Conteudo em bytes.

        Raises:
            RuntimeError se todas as tentativas falharem.
        """
        last_exc: Exception | None = None

        for attempt in range(1, self._settings.MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=self._download_timeout) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    return response.content
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                logger.warning(
                    "Tentativa %d/%d falhou para download %s: %s",
                    attempt,
                    self._settings.MAX_RETRIES,
                    url,
                    exc,
                )
                if attempt < self._settings.MAX_RETRIES:
                    import asyncio

                    await asyncio.sleep(2 ** (attempt - 1))
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "Erro HTTP %d ao baixar %s: %s",
                    exc.response.status_code,
                    url,
                    exc,
                )
                raise

        raise last_exc or RuntimeError(
            f"Falha apos {self._settings.MAX_RETRIES} tentativas para {url}"
        )

    @staticmethod
    def compute_checksum(content: bytes) -> str:
        """
        Computa hash SHA-256 do conteudo.

        Args:
            content: bytes do artefato.

        Returns:
            Hex digest do SHA-256.
        """
        return hashlib.sha256(content).hexdigest()

    def store_artifact(
        self,
        stable_key: str,
        content: bytes,
        fmt: str,
    ) -> str:
        """
        Armazena artefato no MinIO com chave deterministica.

        Chave: {provider}/{source_id}/{version}.{format}
        Para Gutenberg: gutenberg/{gutenberg_id}/v1.{format}
        Para Open Library: openlibrary/{ol_key_slug}/v1.{format}

        Args:
            stable_key: chave estavel do livro (ex: gutenberg:12345).
            content: conteudo do artefato em bytes.
            fmt: formato do arquivo (txt, epub, pdf).

        Returns:
            Chave do artefato no MinIO.
        """
        # Parseia stable_key para construir artifact_key
        artifact_key = self._build_artifact_key(stable_key, fmt)

        # Upload para MinIO
        data = io.BytesIO(content)
        content_type = self._content_type_for_format(fmt)

        self._minio.put_object(
            bucket_name=self._bucket,
            object_name=artifact_key,
            data=data,
            length=len(content),
            content_type=content_type,
        )

        logger.info(
            "Artefato armazenado: key=%s, size=%d, format=%s",
            artifact_key,
            len(content),
            fmt,
        )
        return artifact_key

    def get_artifact(self, artifact_key: str) -> bytes:
        """
        Baixa artefato do MinIO.

        Args:
            artifact_key: chave do artefato no MinIO.

        Returns:
            Conteudo em bytes.
        """
        response = self._minio.get_object(
            bucket_name=self._bucket,
            object_name=artifact_key,
        )
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    @staticmethod
    def _build_artifact_key(stable_key: str, fmt: str) -> str:
        """
        Constroi chave deterministica para o artefato no MinIO.

        Args:
            stable_key: chave estavel (ex: gutenberg:12345, ol:/works/OL123W).
            fmt: formato do arquivo.

        Returns:
            Chave URL-safe para MinIO.
        """
        if ":" in stable_key:
            provider, source_id = stable_key.split(":", 1)
        else:
            provider = "unknown"
            source_id = stable_key

        # Sanitiza source_id para ser URL-safe
        source_id = source_id.replace("/", "_").replace(" ", "_")

        return f"{provider}/{source_id}/v1.{fmt}"

    @staticmethod
    def _content_type_for_format(fmt: str) -> str:
        """
        Retorna Content-Type baseado no formato.

        Args:
            fmt: formato do arquivo.

        Returns:
            MIME type correspondente.
        """
        content_types = {
            "txt": "text/plain",
            "epub": "application/epub+zip",
            "pdf": "application/pdf",
            "html": "text/html",
            "kindle": "application/x-mobipocket-ebook",
            "mobi": "application/x-mobipocket-ebook",
        }
        return content_types.get(fmt.lower(), "application/octet-stream")
