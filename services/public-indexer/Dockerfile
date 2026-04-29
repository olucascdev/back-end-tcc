# =============================================================================
# Public Indexer — Dockerfile
# =============================================================================
# Imagem leve baseada em Python 3.11-slim.
# Instala dependencias, copia codigo e expoe porta 8001.
# =============================================================================

FROM python:3.11-slim AS base

# Evita cache do pip e gera bytecode
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Instala dependencias primeiro (cache de camada Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia codigo fonte
COPY app/ ./app/

# Usuario nao-root para seguranca
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8001/api/v1/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
