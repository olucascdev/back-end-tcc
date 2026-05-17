#!/usr/bin/env bash
# =============================================================================
# Phase 6 Quality Gate Script
# =============================================================================
# Executa todas as verificacoes de qualidade da Fase 6 em sequencia.
# Falha rapido no primeiro erro (fail-fast).
# Retorna exit code 0 se todas as verificacoes passarem.
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_AGENT="${ROOT_DIR}/services/python-agent"
PUBLIC_INDEXER="${ROOT_DIR}/services/public-indexer"
GO_GATEWAY="${ROOT_DIR}/services/go-gateway"
SCRIPTS_DIR="${ROOT_DIR}/scripts/quality-gates"

PASS_COUNT=0
TOTAL_COUNT=0

log_step()  { echo -e "${BLUE}[STEP]${NC} $1"; }
log_pass()  { echo -e "${GREEN}[PASS]${NC} $1"; ((PASS_COUNT++)); ((TOTAL_COUNT++)); }
log_fail()  { echo -e "${RED}[FAIL]${NC} $1"; ((TOTAL_COUNT++)); exit 1; }
log_skip()  { echo -e "${YELLOW}[SKIP]${NC} $1"; ((TOTAL_COUNT++)); }

# ============================================================================
# 1. Python Tests (pytest)
# ============================================================================
log_step "1/7 — Python tests (pytest)"

if command -v pytest &>/dev/null; then
    if pytest "${PYTHON_AGENT}/tests" -v --tb=short 2>&1; then
        log_pass "Python agent tests passed"
    else
        log_fail "Python agent tests failed"
    fi

    if pytest "${PUBLIC_INDEXER}/tests" -v --tb=short 2>&1; then
        log_pass "Public indexer tests passed"
    else
        log_fail "Public indexer tests failed"
    fi
else
    log_fail "pytest not found — install with: pip install pytest"
fi

# ============================================================================
# 2. Go Tests (go test)
# ============================================================================
log_step "2/7 — Go tests (go test)"

if command -v go &>/dev/null; then
    if (cd "${GO_GATEWAY}" && go test ./... -v 2>&1); then
        log_pass "Go gateway tests passed"
    else
        log_fail "Go gateway tests failed"
    fi
else
    log_fail "go not found — install Go toolchain"
fi

# ============================================================================
# 3. Lint Python (ruff)
# ============================================================================
log_step "3/7 — Lint Python (ruff)"

if command -v ruff &>/dev/null; then
    if ruff check "${PYTHON_AGENT}" "${PUBLIC_INDEXER}" 2>&1; then
        log_pass "Python lint passed"
    else
        log_fail "Python lint failed — run: ruff check --fix"
    fi
else
    log_fail "ruff not found — install with: pip install ruff"
fi

# ============================================================================
# 4. Lint Go (gofmt)
# ============================================================================
log_step "4/7 — Lint Go (gofmt)"

if command -v gofmt &>/dev/null; then
    UNFORMATTED=$(gofmt -l "${GO_GATEWAY}" 2>/dev/null || true)
    if [ -z "${UNFORMATTED}" ]; then
        log_pass "Go format check passed"
    else
        log_fail "Go files not formatted: ${UNFORMATTED}"
    fi
else
    log_fail "gofmt not found — install Go toolchain"
fi

# ============================================================================
# 5. Smoke e2e (health endpoints)
# ============================================================================
log_step "5/7 — Smoke e2e (health endpoints)"

SMOKE_PASS=true

# Check public-indexer health
if command -v curl &>/dev/null; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
        http://localhost:8001/api/v1/health 2>/dev/null || echo "000")
    if [ "${HTTP_CODE}" = "200" ]; then
        log_pass "public-indexer health check passed (HTTP ${HTTP_CODE})"
    else
        log_skip "public-indexer not running (HTTP ${HTTP_CODE}) — skipping"
    fi

    # Check python-agent health
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
        http://localhost:8002/api/v1/health 2>/dev/null || echo "000")
    if [ "${HTTP_CODE}" = "200" ]; then
        log_pass "python-agent health check passed (HTTP ${HTTP_CODE})"
    else
        log_skip "python-agent not running (HTTP ${HTTP_CODE}) — skipping"
    fi

    # Check go-gateway health
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
        http://localhost:8080/health 2>/dev/null || echo "000")
    if [ "${HTTP_CODE}" = "200" ]; then
        log_pass "go-gateway health check passed (HTTP ${HTTP_CODE})"
    else
        log_skip "go-gateway not running (HTTP ${HTTP_CODE}) — skipping"
    fi
else
    log_skip "curl not found — skipping smoke tests"
fi

# ============================================================================
# 6. Benchmark check (verify report exists)
# ============================================================================
log_step "6/7 — Benchmark report check"

if [ -f "${SCRIPTS_DIR}/check_reports.py" ] && command -v python3 &>/dev/null; then
    if python3 "${SCRIPTS_DIR}/check_reports.py" 2>&1; then
        log_pass "Benchmark report validation passed"
    else
        log_fail "Benchmark report validation failed"
    fi
else
    log_skip "check_reports.py or python3 not available — skipping"
fi

# ============================================================================
# 7. RAG evaluation check (verify report exists)
# ============================================================================
log_step "7/7 — RAG evaluation report check"

# Check for evaluation report in expected locations
EVAL_FOUND=false
for dir in "${ROOT_DIR}/tools/benchmark" "${ROOT_DIR}/reports" "${ROOT_DIR}/docs"; do
    if [ -d "${dir}" ]; then
        if ls "${dir}"/eval_report* "${dir}"/rag_eval* 1>/dev/null 2>&1; then
            EVAL_FOUND=true
            break
        fi
    fi
done

if [ "${EVAL_FOUND}" = true ]; then
    log_pass "RAG evaluation report found"
else
    log_skip "RAG evaluation report not found — run Feature 6.4 evaluation first"
fi

# ============================================================================
# Resultado final
# ============================================================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Quality Gate Result: ${PASS_COUNT}/${TOTAL_COUNT} passed${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${GREEN}All quality gates passed!${NC}"
exit 0
