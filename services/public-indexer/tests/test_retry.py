"""
Testes do RetryPolicy.

Verifica backoff exponencial, jitter e filtragem de erros transientes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.infrastructure.retry import RetryPolicy, with_retry


class TestRetryPolicyConfig:
    """Testes de configuracao do retry."""

    def test_default_config(self) -> None:
        """Verifica configuracoes default."""
        policy = RetryPolicy()
        assert policy._max_retries == 3
        assert policy._base_delay == 1.0
        assert policy._max_delay == 30.0
        assert policy._jitter is True

    def test_custom_config(self) -> None:
        """Verifica configuracoes customizadas."""
        policy = RetryPolicy(
            max_retries=5, base_delay=2.0, max_delay=60.0, jitter=False
        )
        assert policy._max_retries == 5
        assert policy._base_delay == 2.0
        assert policy._max_delay == 60.0
        assert policy._jitter is False


class TestDelayCalculation:
    """Testes de calculo de delay."""

    def test_exponential_backoff(self) -> None:
        """Verifica backoff exponencial."""
        policy = RetryPolicy(base_delay=1.0, jitter=False)

        assert policy.calculate_delay(0) == 1.0  # 1 * 2^0
        assert policy.calculate_delay(1) == 2.0  # 1 * 2^1
        assert policy.calculate_delay(2) == 4.0  # 1 * 2^2
        assert policy.calculate_delay(3) == 8.0  # 1 * 2^3

    def test_max_delay_cap(self) -> None:
        """Verifica que delay nao excede max_delay."""
        policy = RetryPolicy(base_delay=1.0, max_delay=10.0, jitter=False)

        # 2^10 = 1024, mas deve ser capped em 10
        assert policy.calculate_delay(10) == 10.0

    def test_jitter_adds_randomness(self) -> None:
        """Verifica que jitter adiciona variacao."""
        policy = RetryPolicy(base_delay=1.0, jitter=True)

        delays = [policy.calculate_delay(0) for _ in range(10)]
        # Com jitter, delays devem variar entre 0.5 e 1.0
        assert all(0.5 <= d <= 1.0 for d in delays)
        # Deve haver alguma variacao
        assert len(set(delays)) > 1


class TestTransientErrorDetection:
    """Testes de deteccao de erros transientes."""

    def test_connection_error_is_transient(self) -> None:
        """Verifica que ConnectionError e transiente."""
        assert RetryPolicy.is_transient_error(ConnectionError()) is True

    def test_timeout_error_is_transient(self) -> None:
        """Verifica que TimeoutError e transiente."""
        assert RetryPolicy.is_transient_error(TimeoutError()) is True

    def test_os_error_is_transient(self) -> None:
        """Verifica que OSError e transiente."""
        assert RetryPolicy.is_transient_error(OSError()) is True

    def test_value_error_is_not_transient(self) -> None:
        """Verifica que ValueError nao e transiente."""
        assert RetryPolicy.is_transient_error(ValueError("bad input")) is False

    def test_timeout_string_is_transient(self) -> None:
        """Verifica que mensagem com 'timeout' e transiente."""
        assert RetryPolicy.is_transient_error(RuntimeError("Request timeout")) is True

    def test_503_string_is_transient(self) -> None:
        """Verifica que mensagem com '503' e transiente."""
        assert RetryPolicy.is_transient_error(RuntimeError("HTTP 503")) is True

    def test_rate_limit_string_is_transient(self) -> None:
        """Verifica que mensagem com 'rate limit' e transiente."""
        assert (
            RetryPolicy.is_transient_error(RuntimeError("Rate limit exceeded")) is True
        )


class TestRetryExecution:
    """Testes de execucao com retry."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self) -> None:
        """Verifica sucesso na primeira tentativa."""
        policy = RetryPolicy(max_retries=3)

        async def success_fn() -> str:
            return "ok"

        result = await policy.execute(success_fn)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self) -> None:
        """Verifica retry em falha transiente."""
        policy = RetryPolicy(max_retries=3, base_delay=0.01, jitter=False)

        call_count = 0

        async def flaky_fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection refused")
            return "ok"

        result = await policy.execute(flaky_fn)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_permanent_failure(self) -> None:
        """Verifica que erro permanente nao e retentado."""
        policy = RetryPolicy(max_retries=3)

        call_count = 0

        async def permanent_fail_fn() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid input")

        with pytest.raises(ValueError, match="Invalid input"):
            await policy.execute(permanent_fail_fn)

        assert call_count == 1  # Apenas uma tentativa

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self) -> None:
        """Verifica que excecao e lancada apos max retries."""
        policy = RetryPolicy(max_retries=2, base_delay=0.01, jitter=False)

        async def always_fail_fn() -> str:
            raise TimeoutError("Always timeout")

        with pytest.raises(TimeoutError):
            await policy.execute(always_fail_fn)


class TestRetryDecorator:
    """Testes do decorator de retry."""

    @pytest.mark.asyncio
    async def test_decorator_retries(self) -> None:
        """Verifica que decorator aplica retry."""
        policy = RetryPolicy(max_retries=2, base_delay=0.01, jitter=False)

        call_count = 0

        @policy.decorator
        async def flaky_fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Transient")
            return "ok"

        result = await flaky_fn()
        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_with_retry_factory(self) -> None:
        """Verifica factory de decorator."""
        call_count = 0

        @with_retry(max_retries=2, base_delay=0.01, max_delay=1.0)
        async def flaky_fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Timeout")
            return "ok"

        result = await flaky_fn()
        assert result == "ok"
        assert call_count == 2
