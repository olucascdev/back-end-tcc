# =============================================================================
# Public Indexer — Makefile
# =============================================================================
# Targets para gerenciar o servico public-indexer localmente.
# =============================================================================

.PHONY: help install dev test lint format docker-build docker-run

# --- Variaveis ---
SERVICE_NAME := public-indexer
PORT := 8001

# --- Help ---
help: ## Mostra os targets disponiveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

# --- Desenvolvimento ---
install: ## Instala dependencias em venv
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt

dev: ## Executa servidor com hot-reload
	uvicorn app.main:app --reload --host 0.0.0.0 --port $(PORT)

# --- Quality Gates ---
test: ## Executa testes com pytest
	pytest tests/ -v

lint: ## Executa lint com ruff
	ruff check .

format: ## Formata codigo com black
	black .

# --- Docker ---
docker-build: ## Constroi imagem Docker
	docker build -t $(SERVICE_NAME):latest .

docker-run: ## Executa container Docker
	docker run --rm -p $(PORT):8001 --env-file .env $(SERVICE_NAME):latest
