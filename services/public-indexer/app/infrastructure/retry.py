"""
Politica de retry com backoff exponencial e jitter.

Decorator e funcao utilitaria para operacoes assincronas com
retry configuravel apenas em erros transientes.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Callable, Coroutine, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Erros transientes que justificam retry
TRANSIENT_ERRORS = (
    ConnectionError,
    TimeoutError,
    OSError,
)


class RetryPolicy:
    """
    Politica de retry com backoff exponencial + jitter.

    Apenas retenta em erros transientes (timeout, conexao, 5xx).
    Erros permanentes (4xx, validacao) nao sao retentados.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: bool = True,
    ) -> None:
        """
        Inicializa politica de retry.

        Args:
            max_retries: numero maximo de tentativas.
            base_delay: delay base em segundos para backoff.
            max_delay: delay maximo em segundos.
            jitter: se True, adiciona jitter aleatorio ao delay.
        """
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """
        Calcula delay para uma tentativa com backoff exponencial.

        Args:
            attempt: numero da tentativa (0-based).

        Returns:
            Delay em segundos.
        """
        delay = min(self._base_delay * (2**attempt), self._max_delay)
        if self._jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        return delay

    @staticmethod
    def is_transient_error(exc: Exception) -> bool:
        """
        Verifica se excecao e transiente (retryavel).

        Args:
            exc: excecao capturada.

        Returns:
            True se erro e transiente.
        """
        # Verifica tipo de excecao
        if isinstance(exc, TRANSIENT_ERRORS):
            return True

        # Verifica mensagem de erro para casos de HTTP/timeout
        error_str = str(exc).lower()
        transient_keywords = [
            "timeout",
            "connection",
            "refused",
            "reset",
            "unavailable",
            "502",
            "503",
            "504",
            "rate limit",
            "429",
            "500",
        ]
        return any(keyword in error_str for keyword in transient_keywords)

    async def execute(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Executa funcao assincrona com retry.

        Args:
            func: funcao assincrona a executar.
            *args: argumentos posicionais.
            **kwargs: argumentos nomeados.

        Returns:
            Resultado da funcao.

        Raises:
            Ultima excecao capturada se todas as tentativas falharem.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc

                if not self.is_transient_error(exc):
                    logger.error(
                        "Erro permanente, sem retry: %s",
                        exc,
                    )
                    raise

                if attempt < self._max_retries:
                    delay = self.calculate_delay(attempt)
                    logger.warning(
                        "Retry: func=%s, attempt=%d/%d, delay=%.2fs, error=%s",
                        func.__name__ if hasattr(func, "__name__") else str(func),
                        attempt + 1,
                        self._max_retries + 1,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Retry esgotado: func=%s, attempts=%d, error=%s",
                        func.__name__ if hasattr(func, "__name__") else str(func),
                        self._max_retries + 1,
                        exc,
                    )

        raise last_exc or RuntimeError("Retry falhou sem excecao capturada")

    def decorator(
        self, func: Callable[..., Coroutine[Any, Any, T]]
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        """
        Decorator para aplicar retry a uma funcao assincrona.

        Args:
            func: funcao assincrona a decorar.

        Returns:
            Funcao decorada com retry.
        """

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await self.execute(func, *args, **kwargs)

        return wrapper


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Callable:
    """
    Factory de decorator com retry configuravel.

    Args:
        max_retries: numero maximo de tentativas.
        base_delay: delay base em segundos.
        max_delay: delay maximo em segundos.

    Returns:
        Decorator configurado.
    """
    policy = RetryPolicy(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
    )
    return policy.decorator
