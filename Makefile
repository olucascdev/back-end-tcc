# =============================================================================
# TCC Backend - Makefile
# =============================================================================
# Targets para gerenciar infraestrutura local e migracoes.
# =============================================================================

.PHONY: help migrate-up migrate-up-postgres migrate-up-mongo \
        infra-up infra-down infra-clean test-migrations \
        lint-python format-python test-python \
        lint-go test-go quality-check

# --- Variaveis ---
POSTGRES_HOST ?= localhost
POSTGRES_PORT ?= 5432
POSTGRES_USER ?= tcc_user
POSTGRES_PASSWORD ?= tcc_pass
POSTGRES_DB ?= tcc_db

MONGO_HOST ?= localhost
MONGO_PORT ?= 27017
MONGO_USER ?= tcc_mongo_user
MONGO_PASSWORD ?= tcc_mongo_pass
MONGO_DB ?= tcc_catalog

MIGRATIONS_DIR := infra/migrations

# --- Help ---
help: ## Mostra os targets disponiveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

# --- Infraestrutura ---
infra-up: ## Sobe todos os servicos (postgres, redis, mongodb, minio)
	docker compose up -d

infra-down: ## Para todos os servicos
	docker compose down

infra-clean: ## Para servicos e remove volumes
	docker compose down -v

# --- Migracoes ---
migrate-up: migrate-up-postgres migrate-up-mongo ## Aplica todas as migracoes (PostgreSQL + MongoDB)

migrate-up-postgres: ## Aplica apenas migracoes PostgreSQL
	@echo "[Make] Aplicando migracoes PostgreSQL..."
	@POSTGRES_HOST=$(POSTGRES_HOST) \
	 POSTGRES_PORT=$(POSTGRES_PORT) \
	 POSTGRES_USER=$(POSTGRES_USER) \
	 POSTGRES_PASSWORD=$(POSTGRES_PASSWORD) \
	 POSTGRES_DB=$(POSTGRES_DB) \
	 bash $(MIGRATIONS_DIR)/apply_migrations.sh --postgres-only

migrate-up-mongo: ## Aplica apenas migracoes MongoDB
	@echo "[Make] Aplicando migracoes MongoDB..."
	@MONGO_HOST=$(MONGO_HOST) \
	 MONGO_PORT=$(MONGO_PORT) \
	 MONGO_USER=$(MONGO_USER) \
	 MONGO_PASSWORD=$(MONGO_PASSWORD) \
	 MONGO_DB=$(MONGO_DB) \
	 bash $(MIGRATIONS_DIR)/apply_migrations.sh --mongo-only

# --- Testes ---
test-migrations: infra-up ## Sobe infra, aplica migracoes, verifica e para
	@echo ""
	@echo "=== Aguardando PostgreSQL ficar pronto ==="
	@for i in $$(seq 1 30); do \
		if docker compose exec -T postgres pg_isready -U $(POSTGRES_USER) -d $(POSTGRES_DB) 2>/dev/null; then \
			echo "PostgreSQL pronto!"; \
			break; \
		fi; \
		echo "Aguardando... ($$i/30)"; \
		sleep 2; \
	done
	@echo ""
	@echo "=== Aguardando MongoDB ficar pronto ==="
	@for i in $$(seq 1 30); do \
		if docker compose exec -T mongodb mongosh --quiet --eval "db.adminCommand('ping')" 2>/dev/null; then \
			echo "MongoDB pronto!"; \
			break; \
		fi; \
		echo "Aguardando... ($$i/30)"; \
		sleep 2; \
	done
	@echo ""
	@echo "=== Aplicando migracoes ==="
	@$(MAKE) migrate-up
	@echo ""
	@echo "=== Verificando tabelas PostgreSQL ==="
	@docker compose exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "\dt"
	@echo ""
	@echo "=== Verificando indices PostgreSQL ==="
	@docker compose exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "\di"
	@echo ""
	@echo "=== Verificando collections MongoDB ==="
	@docker compose exec -T mongodb mongosh --quiet --eval 'use tcc_catalog; db.getCollectionNames()'
	@echo ""
	@echo "=== Verificando schema validation MongoDB ==="
	@docker compose exec -T mongodb mongosh --quiet --eval 'use tcc_catalog; db.getCollectionInfos({name: "books"})[0].options.validator'
	@echo ""
	@echo "=== Teste de migracoes concluido ==="
	@echo ""
	@echo "Parando containers..."
	@$(MAKE) infra-down

# --- Quality Gates ---
PYTHON_SERVICE := services/python-agent
GO_SERVICE := services/go-gateway

lint-python: ## Executa lint Python com ruff
	ruff check $(PYTHON_SERVICE)

format-python: ## Formata codigo Python com black
	black $(PYTHON_SERVICE)

test-python: ## Executa testes Python com pytest
	pytest $(PYTHON_SERVICE)/tests -v

lint-go: ## Executa lint Go (gofmt + golint se disponivel)
	@gofmt -l $(GO_SERVICE) | grep -q . && { echo "Go files not formatted:"; gofmt -l $(GO_SERVICE); exit 1; } || echo "Go format OK"
	@command -v golint &>/dev/null && golint $(GO_SERVICE)/... || echo "golint not found, skipping"

test-go: ## Executa testes Go
	cd $(GO_SERVICE) && go test ./... -v

quality-check: lint-python test-python lint-go test-go ## Executa todos os checks de qualidade (lint + test Python e Go)
