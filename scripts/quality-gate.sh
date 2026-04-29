#!/usr/bin/env bash
# =============================================================================
# Quality Gate Script — Validacao de qualidade e conformidade
# =============================================================================
# Executa testes Python e Go, verifica thresholds de cobertura e gera
# relatorio de conformidade em reports/quality-gate-report.md.
#
# Thresholds:
#   Python test coverage >= 70%
#   Go test coverage    >= 60%
#
# Exit code:
#   0 — todos os gates passaram
#   1 — um ou mais gates falharam
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS_DIR="${ROOT_DIR}/reports"
REPORT_FILE="${REPORTS_DIR}/quality-gate-report.md"
TIMESTAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

PYTHON_AGENT="${ROOT_DIR}/services/python-agent"
GO_GATEWAY="${ROOT_DIR}/services/go-gateway"

# Thresholds de cobertura
PYTHON_COV_THRESHOLD=70
GO_COV_THRESHOLD=60

# Contadores
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

mkdir -p "${REPORTS_DIR}"

log_pass()  { echo -e "${GREEN}[PASS]${NC} $1"; ((PASS_COUNT++)); }
log_fail()  { echo -e "${RED}[FAIL]${NC} $1"; ((FAIL_COUNT++)); }
log_skip()  { echo -e "${YELLOW}[SKIP]${NC} $1"; ((SKIP_COUNT++)); }
log_step()  { echo -e "${BLUE}[STEP]${NC} $1"; }

# Inicializar relatorio
cat > "${REPORT_FILE}" <<HEADER
# Relatorio de Quality Gate

**Data:** ${TIMESTAMP}
**Commit:** $(git rev-parse --short HEAD 2>/dev/null || echo "N/A")
**Branch:** $(git branch --show-current 2>/dev/null || echo "N/A")

## Resumo

| Gate | Resultado | Detalhe |
|---|---|---|
HEADER

# ---------------------------------------------------------------------------
# 1. Python Tests (pytest)
# ---------------------------------------------------------------------------
log_step "1/4 — Python tests (pytest)"

PYTHON_TEST_RESULT="N/A"
if command -v pytest &>/dev/null; then
    if pytest "${PYTHON_AGENT}/tests" -v --tb=short 2>&1 | tee /tmp/pytest_output.txt; then
        log_pass "Python tests passed"
        PYTHON_TEST_RESULT="PASS"
        echo "| Python tests | PASS | Todos os testes passaram |" >> "${REPORT_FILE}"
    else
        log_fail "Python tests failed"
        PYTHON_TEST_RESULT="FAIL"
        echo "| Python tests | FAIL | Verificar output acima |" >> "${REPORT_FILE}"
    fi
else
    log_skip "pytest not found"
    PYTHON_TEST_RESULT="SKIP"
    echo "| Python tests | SKIP | pytest nao instalado |" >> "${REPORT_FILE}"
fi

# ---------------------------------------------------------------------------
# 2. Python Coverage
# ---------------------------------------------------------------------------
log_step "2/4 — Python coverage (threshold: ${PYTHON_COV_THRESHOLD}%)"

PYTHON_COV_RESULT="N/A"
PYTHON_COV_VALUE="N/A"
if command -v pytest &>/dev/null; then
    COV_OUTPUT=$(pytest "${PYTHON_AGENT}/tests" --cov=app --cov-report=term-missing --no-header -q 2>&1 || true)
    # Extrair porcentagem de cobertura total (linha "TOTAL")
    PYTHON_COV_VALUE=$(echo "${COV_OUTPUT}" | grep -i "TOTAL" | grep -oP '\d+(?=%)' | tail -1 || echo "0")

    if [ "${PYTHON_COV_VALUE}" != "0" ] && [ "${PYTHON_COV_VALUE}" -ge "${PYTHON_COV_THRESHOLD}" ] 2>/dev/null; then
        log_pass "Python coverage: ${PYTHON_COV_VALUE}% (threshold: ${PYTHON_COV_THRESHOLD}%)"
        PYTHON_COV_RESULT="PASS"
        echo "| Python coverage | PASS | ${PYTHON_COV_VALUE}% >= ${PYTHON_COV_THRESHOLD}% |" >> "${REPORT_FILE}"
    else
        log_fail "Python coverage: ${PYTHON_COV_VALUE}% (threshold: ${PYTHON_COV_THRESHOLD}%)"
        PYTHON_COV_RESULT="FAIL"
        echo "| Python coverage | FAIL | ${PYTHON_COV_VALUE}% < ${PYTHON_COV_THRESHOLD}% |" >> "${REPORT_FILE}"
    fi
else
    log_skip "pytest not found"
    PYTHON_COV_RESULT="SKIP"
    echo "| Python coverage | SKIP | pytest nao instalado |" >> "${REPORT_FILE}"
fi

# ---------------------------------------------------------------------------
# 3. Go Tests + Coverage
# ---------------------------------------------------------------------------
log_step "3/4 — Go tests + coverage (threshold: ${GO_COV_THRESHOLD}%)"

GO_TEST_RESULT="N/A"
GO_COV_RESULT="N/A"
GO_COV_VALUE="N/A"

if command -v go &>/dev/null; then
    # Executar testes com cobertura
    GO_COV_OUTPUT=$(cd "${GO_GATEWAY}" && go test ./... -cover 2>&1 || true)

    # Verificar se testes passaram
    if echo "${GO_COV_OUTPUT}" | grep -q "FAIL"; then
        log_fail "Go tests failed"
        GO_TEST_RESULT="FAIL"
        echo "| Go tests | FAIL | Verificar output acima |" >> "${REPORT_FILE}"
    else
        log_pass "Go tests passed"
        GO_TEST_RESULT="PASS"
        echo "| Go tests | PASS | Todos os testes passaram |" >> "${REPORT_FILE}"
    fi

    # Extrair cobertura total
    GO_COV_VALUE=$(echo "${GO_COV_OUTPUT}" | grep -oP 'coverage:\s*\K\d+\.\d+' | tail -1 || echo "0")

    # Comparar com threshold (usando awk para comparacao float)
    COV_MET=$(echo "${GO_COV_VALUE} ${GO_COV_THRESHOLD}" | awk '{if ($1 >= $2) print "PASS"; else print "FAIL"}')

    if [ "${COV_MET}" = "PASS" ]; then
        log_pass "Go coverage: ${GO_COV_VALUE}% (threshold: ${GO_COV_THRESHOLD}%)"
        GO_COV_RESULT="PASS"
        echo "| Go coverage | PASS | ${GO_COV_VALUE}% >= ${GO_COV_THRESHOLD}% |" >> "${REPORT_FILE}"
    else
        log_fail "Go coverage: ${GO_COV_VALUE}% (threshold: ${GO_COV_THRESHOLD}%)"
        GO_COV_RESULT="FAIL"
        echo "| Go coverage | FAIL | ${GO_COV_VALUE}% < ${GO_COV_THRESHOLD}% |" >> "${REPORT_FILE}"
    fi
else
    log_skip "go not found"
    GO_TEST_RESULT="SKIP"
    GO_COV_RESULT="SKIP"
    echo "| Go tests | SKIP | Go nao instalado |" >> "${REPORT_FILE}"
    echo "| Go coverage | SKIP | Go nao instalado |" >> "${REPORT_FILE}"
fi

# ---------------------------------------------------------------------------
# 4. Lint checks
# ---------------------------------------------------------------------------
log_step "4/4 — Lint checks (ruff + gofmt)"

LINT_RESULT="N/A"
LINT_PASS=true

# Python lint
if command -v ruff &>/dev/null; then
    if ruff check "${PYTHON_AGENT}" 2>&1; then
        log_pass "Python lint (ruff) passed"
    else
        log_fail "Python lint (ruff) failed"
        LINT_PASS=false
    fi
else
    log_skip "ruff not found"
fi

# Go format
if command -v gofmt &>/dev/null; then
    UNFORMATTED=$(gofmt -l "${GO_GATEWAY}" 2>/dev/null || true)
    if [ -z "${UNFORMATTED}" ]; then
        log_pass "Go format (gofmt) passed"
    else
        log_fail "Go format (gofmt) failed: ${UNFORMATTED}"
        LINT_PASS=false
    fi
else
    log_skip "gofmt not found"
fi

if [ "${LINT_PASS}" = true ]; then
    LINT_RESULT="PASS"
    echo "| Lint checks | PASS | ruff + gofmt OK |" >> "${REPORT_FILE}"
else
    LINT_RESULT="FAIL"
    echo "| Lint checks | FAIL | Verificar falhas acima |" >> "${REPORT_FILE}"
fi

# ---------------------------------------------------------------------------
# Finalizar relatorio
# ---------------------------------------------------------------------------

TOTAL=$((PASS_COUNT + FAIL_COUNT + SKIP_COUNT))

cat >> "${REPORT_FILE}" <<FOOTER

## Contagem final

| Status | Quantidade |
|---|---|
| Pass | ${PASS_COUNT} |
| Fail | ${FAIL_COUNT} |
| Skip | ${SKIP_COUNT} |
| Total | ${TOTAL} |

## Thresholds de cobertura

| Linguagem | Threshold | Resultado |
|---|---|---|
| Python | >= ${PYTHON_COV_THRESHOLD}% | ${PYTHON_COV_VALUE}% (${PYTHON_COV_RESULT}) |
| Go | >= ${GO_COV_THRESHOLD}% | ${GO_COV_VALUE}% (${GO_COV_RESULT}) |

## Conclusao

FOOTER

if [ "${FAIL_COUNT}" -eq 0 ]; then
    echo -e "${GREEN}**QUALITY GATE PASSED** — Todos os checks passaram.${NC}" >> "${REPORT_FILE}"
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Quality Gate PASSED: ${PASS_COUNT}/${TOTAL} checks${NC}"
    echo -e "${GREEN}========================================${NC}"
    exit 0
else
    echo -e "${RED}**QUALITY GATE FAILED** — ${FAIL_COUNT} check(s) falharam.${NC}" >> "${REPORT_FILE}"
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  Quality Gate FAILED: ${FAIL_COUNT}/${TOTAL} checks${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
