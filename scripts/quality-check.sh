#!/usr/bin/env bash
# Script de validacao pre-commit para qualidade de codigo.
# Executa lint e testes de ambos servicos (Python e Go).
# Retorna exit code != 0 se qualquer verificacao falhar.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXIT_CODE=0

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ---------------------------------------------------------------------------
# Python: lint
# ---------------------------------------------------------------------------
log_info "Running Python lint (ruff)..."
if command -v ruff &>/dev/null; then
    if ! ruff check "${ROOT_DIR}/services/python-agent"; then
        log_error "Python lint failed"
        EXIT_CODE=1
    else
        log_info "Python lint passed"
    fi
else
    log_warn "ruff not found, skipping Python lint"
fi

# ---------------------------------------------------------------------------
# Python: tests
# ---------------------------------------------------------------------------
log_info "Running Python tests (pytest)..."
if command -v pytest &>/dev/null; then
    if ! pytest "${ROOT_DIR}/services/python-agent/tests" -v; then
        log_error "Python tests failed"
        EXIT_CODE=1
    else
        log_info "Python tests passed"
    fi
else
    log_warn "pytest not found, skipping Python tests"
fi

# ---------------------------------------------------------------------------
# Go: lint (gofmt)
# ---------------------------------------------------------------------------
log_info "Running Go lint (gofmt)..."
GO_SERVICE="${ROOT_DIR}/services/go-gateway"
if command -v gofmt &>/dev/null; then
    UNFORMATTED=$(gofmt -l "${GO_SERVICE}" 2>/dev/null || true)
    if [ -n "${UNFORMATTED}" ]; then
        log_error "Go files not formatted: ${UNFORMATTED}"
        EXIT_CODE=1
    else
        log_info "Go lint passed"
    fi
else
    log_warn "gofmt not found, skipping Go lint"
fi

# ---------------------------------------------------------------------------
# Go: tests
# ---------------------------------------------------------------------------
log_info "Running Go tests..."
if command -v go &>/dev/null; then
    if ! (cd "${GO_SERVICE}" && go test ./...); then
        log_error "Go tests failed"
        EXIT_CODE=1
    else
        log_info "Go tests passed"
    fi
else
    log_warn "go not found, skipping Go tests"
fi

# ---------------------------------------------------------------------------
# Resultado final
# ---------------------------------------------------------------------------
if [ ${EXIT_CODE} -eq 0 ]; then
    log_info "All quality checks passed"
else
    log_error "Some quality checks failed"
fi

exit ${EXIT_CODE}
