"""
Cliente MinIO/S3 para download de arquivos de documento.

Usa boto3 para comunicacao com armazenamento S3-compatible.
Configuravel via variaveis de ambiente (MINIO_ENDPOINT, MINIO_ACCESS_KEY, etc).
"""

from __future__ import annotations

import logging
from io import BytesIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings

logger = logging.getLogger(__name__)


class MinIOClient:
    """Wrapper thin sobre boto3 para operacoes de storage."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._client = boto3.client(
            "s3",
            endpoint_url=f"http://{self._settings.MINIO_ENDPOINT}",
            aws_access_key_id=self._settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=self._settings.MINIO_SECRET_KEY,
            # Desabilita verificacao SSL para desenvolvimento local com MinIO
            verify=False,
        )

    def download_file(self, storage_key: str, bucket: str | None = None) -> bytes:
        """Baixa arquivo do bucket e retorna conteudo como bytes.

        Args:
            storage_key: chave/caminho do objeto no bucket.
            bucket: nome do bucket; usa default do settings se None.

        Returns:
            Conteudo binario do arquivo.

        Raises:
            FileNotFoundError: se o objeto nao existe no bucket.
            StorageError: se houver erro de conexao ou permissao.
        """
        bucket_name = bucket or self._settings.MINIO_BUCKET
        try:
            response = self._client.get_object(Bucket=bucket_name, Key=storage_key)
            return response["Body"].read()
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            if error_code == "NoSuchKey":
                logger.error(
                    "Objeto nao encontrado: bucket=%s key=%s", bucket_name, storage_key
                )
                raise FileNotFoundError(
                    f"Arquivo nao encontrado: bucket={bucket_name} key={storage_key}"
                ) from exc
            logger.error(
                "Erro MinIO: code=%s bucket=%s key=%s",
                error_code,
                bucket_name,
                storage_key,
            )
            raise StorageError(f"Falha ao acessar storage: {error_code}") from exc
        except BotoCoreError as exc:
            logger.error("Erro de conexao MinIO: %s", exc)
            raise StorageError(f"Erro de conexao com storage: {exc}") from exc

    def upload_file(
        self, file_bytes: bytes, storage_key: str, bucket: str | None = None
    ) -> str:
        """Envia bytes para o bucket e retorna a chave do objeto.

        Args:
            file_bytes: conteudo binario a enviar.
            storage_key: chave/caminho destino no bucket.
            bucket: nome do bucket; usa default do settings se None.

        Returns:
            A chave do objeto enviado.

        Raises:
            StorageError: se houver erro no upload.
        """
        bucket_name = bucket or self._settings.MINIO_BUCKET
        try:
            self._client.upload_fileobj(BytesIO(file_bytes), bucket_name, storage_key)
            return storage_key
        except (ClientError, BotoCoreError) as exc:
            logger.error("Erro ao enviar para MinIO: %s", exc)
            raise StorageError(f"Falha no upload: {exc}") from exc


class StorageError(Exception):
    """Erro generico de operacao de storage."""

    pass
