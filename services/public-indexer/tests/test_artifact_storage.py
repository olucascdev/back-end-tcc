"""
Testes do servico ArtifactStorageService.

Verifica selecao de formato, checksum, upload/download MinIO.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.infrastructure.artifact_storage import ArtifactStorageService


@pytest.fixture
def settings() -> Settings:
    """Configuracoes padrao para testes."""
    return Settings()


@pytest.fixture
def mock_minio() -> MagicMock:
    """Mock do cliente MinIO."""
    client = MagicMock()
    client.bucket_exists.return_value = True
    return client


@pytest.fixture
def service(settings: Settings, mock_minio: MagicMock) -> ArtifactStorageService:
    """Servico de artefatos com mock MinIO."""
    return ArtifactStorageService(settings=settings, minio_client=mock_minio)


class TestFormatSelection:
    """Testes de selecao de formato."""

    def test_select_txt_priority(self, service: ArtifactStorageService) -> None:
        """Verifica que txt tem prioridade quando disponivel."""
        formats = ["pdf", "epub", "txt"]
        result = service.select_format(formats)
        assert result == "txt"

    def test_select_epub_when_no_txt(self, service: ArtifactStorageService) -> None:
        """Verifica que epub e selecionado quando txt nao disponivel."""
        formats = ["pdf", "epub"]
        result = service.select_format(formats)
        assert result == "epub"

    def test_select_pdf_only(self, service: ArtifactStorageService) -> None:
        """Verifica que pdf e selecionado quando e unica opcao."""
        formats = ["pdf"]
        result = service.select_format(formats)
        assert result == "pdf"

    def test_select_none_when_no_match(self, service: ArtifactStorageService) -> None:
        """Verifica que retorna None quando nenhum formato disponivel."""
        formats = ["mobi", "kindle"]
        result = service.select_format(formats)
        # mobi e kindle nao estao na prioridade padrao (txt, epub, pdf)
        assert result is None

    def test_select_case_insensitive(self, service: ArtifactStorageService) -> None:
        """Verifica que selecao e case-insensitive."""
        formats = ["TXT", "EPUB"]
        result = service.select_format(formats)
        assert result == "txt"

    def test_select_custom_priority(
        self, settings: Settings, mock_minio: MagicMock
    ) -> None:
        """Verifica prioridade customizada via config."""
        settings.ARTIFACT_FORMAT_PRIORITY = "epub,pdf,txt"
        service = ArtifactStorageService(settings=settings, minio_client=mock_minio)

        formats = ["pdf", "txt", "epub"]
        result = service.select_format(formats)
        assert result == "epub"


class TestChecksum:
    """Testes de checksum SHA-256."""

    def test_compute_checksum_deterministic(
        self, service: ArtifactStorageService
    ) -> None:
        """Verifica que checksum e deterministico."""
        content = b"Hello, World!"
        checksum1 = service.compute_checksum(content)
        checksum2 = service.compute_checksum(content)
        assert checksum1 == checksum2

    def test_compute_checksum_different_content(
        self, service: ArtifactStorageService
    ) -> None:
        """Verifica que conteudos diferentes geram checksums diferentes."""
        checksum1 = service.compute_checksum(b"Content A")
        checksum2 = service.compute_checksum(b"Content B")
        assert checksum1 != checksum2

    def test_compute_checksum_hex_format(self, service: ArtifactStorageService) -> None:
        """Verifica que checksum e hex digest."""
        checksum = service.compute_checksum(b"test")
        assert len(checksum) == 64  # SHA-256 = 64 hex chars
        assert all(c in "0123456789abcdef" for c in checksum)


class TestArtifactKey:
    """Testes de construcao de chave de artefato."""

    def test_build_key_gutenberg(self, service: ArtifactStorageService) -> None:
        """Verifica chave para livro Gutenberg."""
        key = service._build_artifact_key("gutenberg:12345", "txt")
        assert key == "gutenberg/12345/v1.txt"

    def test_build_key_openlibrary(self, service: ArtifactStorageService) -> None:
        """Verifica chave para livro Open Library."""
        key = service._build_artifact_key("ol:/works/OL123W", "epub")
        assert key == "ol/_works_OL123W/v1.epub"

    def test_build_key_unknown_provider(self, service: ArtifactStorageService) -> None:
        """Verifica chave para provider desconhecido."""
        key = service._build_artifact_key("some-key", "pdf")
        assert key == "unknown/some-key/v1.pdf"

    def test_build_key_sanitizes_spaces(self, service: ArtifactStorageService) -> None:
        """Verifica que espacos sao sanitizados."""
        key = service._build_artifact_key("provider:my book", "txt")
        assert " " not in key


class TestStoreArtifact:
    """Testes de armazenamento no MinIO."""

    def test_store_artifact_uploads_to_minio(
        self, service: ArtifactStorageService, mock_minio: MagicMock
    ) -> None:
        """Verifica que artefato e enviado ao MinIO."""
        content = b"Test content"
        artifact_key = service.store_artifact("gutenberg:42", content, "txt")

        assert artifact_key == "gutenberg/42/v1.txt"
        mock_minio.put_object.assert_called_once()

        # Verifica argumentos do put_object
        call_kwargs = mock_minio.put_object.call_args
        assert call_kwargs.kwargs["bucket_name"] == "tcc-public-index"
        assert call_kwargs.kwargs["object_name"] == "gutenberg/42/v1.txt"
        assert call_kwargs.kwargs["length"] == len(content)

    def test_store_artifact_content_type(
        self, service: ArtifactStorageService, mock_minio: MagicMock
    ) -> None:
        """Verifica Content-Type correto por formato."""
        service.store_artifact("gutenberg:1", b"content", "txt")
        call_kwargs = mock_minio.put_object.call_args
        assert call_kwargs.kwargs["content_type"] == "text/plain"

        mock_minio.reset_mock()
        service.store_artifact("gutenberg:2", b"content", "epub")
        call_kwargs = mock_minio.put_object.call_args
        assert call_kwargs.kwargs["content_type"] == "application/epub+zip"

        mock_minio.reset_mock()
        service.store_artifact("gutenberg:3", b"content", "pdf")
        call_kwargs = mock_minio.put_object.call_args
        assert call_kwargs.kwargs["content_type"] == "application/pdf"


class TestGetArtifact:
    """Testes de download do MinIO."""

    def test_get_artifact_returns_content(
        self, service: ArtifactStorageService, mock_minio: MagicMock
    ) -> None:
        """Verifica que artefato e baixado do MinIO."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"Downloaded content"
        mock_minio.get_object.return_value = mock_response

        content = service.get_artifact("gutenberg/42/v1.txt")

        assert content == b"Downloaded content"
        mock_minio.get_object.assert_called_once_with(
            bucket_name="tcc-public-index",
            object_name="gutenberg/42/v1.txt",
        )
        mock_response.close.assert_called_once()
        mock_response.release_conn.assert_called_once()


class TestContentTypeMapping:
    """Testes de mapeamento Content-Type."""

    def test_content_type_txt(self) -> None:
        assert ArtifactStorageService._content_type_for_format("txt") == "text/plain"

    def test_content_type_epub(self) -> None:
        assert (
            ArtifactStorageService._content_type_for_format("epub")
            == "application/epub+zip"
        )

    def test_content_type_pdf(self) -> None:
        assert (
            ArtifactStorageService._content_type_for_format("pdf") == "application/pdf"
        )

    def test_content_type_unknown(self) -> None:
        assert (
            ArtifactStorageService._content_type_for_format("xyz")
            == "application/octet-stream"
        )
