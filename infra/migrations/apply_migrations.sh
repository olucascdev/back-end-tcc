#!/usr/bin/env bash
# =============================================================================
# apply_migrations.sh - Aplica migracoes PostgreSQL e MongoDB
# =============================================================================
# Uso:
#   ./apply_migrations.sh                    # usa variaveis de ambiente
#   ./apply_migrations.sh --postgres-only    # apenas PostgreSQL
#   ./apply_migrations.sh --mongo-only       # apenas MongoDB
#
# Variaveis de ambiente obrigatorias:
#   POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
#   MONGO_HOST, MONGO_PORT, MONGO_USER, MONGO_PASSWORD, MONGO_DB
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POSTGRES_MIGRATIONS_DIR="${SCRIPT_DIR}/postgres"
MONGO_MIGRATIONS_DIR="${SCRIPT_DIR}/mongodb"

# --- Configuracao PostgreSQL (valores padrao para desenvolvimento local) ---
PG_HOST="${POSTGRES_HOST:-localhost}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-tcc_user}"
PG_PASSWORD="${POSTGRES_PASSWORD:-tcc_pass}"
PG_DB="${POSTGRES_DB:-tcc_db}"

# --- Configuracao MongoDB (valores padrao para desenvolvimento local) ---
MONGO_HOST="${MONGO_HOST:-localhost}"
MONGO_PORT="${MONGO_PORT:-27017}"
MONGO_USER="${MONGO_USER:-tcc_mongo_user}"
MONGO_PASSWORD="${MONGO_PASSWORD:-tcc_mongo_pass}"
MONGO_DB="${MONGO_DB:-tcc_catalog}"

# --- Flags ---
POSTGRES_ONLY=false
MONGO_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --postgres-only) POSTGRES_ONLY=true ;;
        --mongo-only)    MONGO_ONLY=true ;;
        --help|-h)
            echo "Uso: $0 [--postgres-only|--mongo-only]"
            exit 0
            ;;
    esac
done

# --- Funcoes auxiliares ---
log_info()  { echo "[INFO]  $*"; }
log_ok()    { echo "[OK]    $*"; }
log_error() { echo "[ERROR] $*" >&2; }

# --- Migracoes PostgreSQL ---
run_postgres_migrations() {
    log_info "Aplicando migracoes PostgreSQL em ${PG_HOST}:${PG_PORT}/${PG_DB}..."

    export PGPASSWORD="${PG_PASSWORD}"

    for migration in "${POSTGRES_MIGRATIONS_DIR}"/*.sql; do
        if [[ ! -f "$migration" ]]; then
            log_error "Nenhuma migracao SQL encontrada em ${POSTGRES_MIGRATIONS_DIR}"
            return 1
        fi

        local filename
        filename="$(basename "$migration")"
        log_info "  Aplicando: ${filename}"

        if psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${PG_DB}" \
                 -f "$migration" -v ON_ERROR_STOP=1; then
            log_ok "  ${filename} aplicado com sucesso"
        else
            log_error "Falha ao aplicar ${filename}"
            return 1
        fi
    done

    unset PGPASSWORD
    log_ok "Todas as migracoes PostgreSQL aplicadas com sucesso"
}

# --- Migracoes MongoDB ---
run_mongo_migrations() {
    log_info "Aplicando migracoes MongoDB em ${MONGO_HOST}:${MONGO_PORT}/${MONGO_DB}..."

    # Monta a URI de conexao
    local MONGO_URI="mongodb://${MONGO_USER}:${MONGO_PASSWORD}@${MONGO_HOST}:${MONGO_PORT}/${MONGO_DB}?authSource=admin"

    for migration in "${MONGO_MIGRATIONS_DIR}"/*.js; do
        if [[ ! -f "$migration" ]]; then
            log_error "Nenhuma migracao JS encontrada em ${MONGO_MIGRATIONS_DIR}"
            return 1
        fi

        local filename
        filename="$(basename "$migration")"
        log_info "  Aplicando: ${filename}"

        # Exporta variaveis para o script JS usar
        if MONGO_DB="${MONGO_DB}" mongosh --quiet "${MONGO_URI}" --file "$migration"; then
            log_ok "  ${filename} aplicado com sucesso"
        else
            log_error "Falha ao aplicar ${filename}"
            return 1
        fi
    done

    log_ok "Todas as migracoes MongoDB aplicadas com sucesso"
}

# --- Execucao principal ---
main() {
    log_info "=== Iniciando aplicacao de migracoes ==="

    if [[ "$POSTGRES_ONLY" == false && "$MONGO_ONLY" == false ]] || [[ "$POSTGRES_ONLY" == true ]]; then
        run_postgres_migrations
    fi

    if [[ "$POSTGRES_ONLY" == false && "$MONGO_ONLY" == false ]] || [[ "$MONGO_ONLY" == true ]]; then
        run_mongo_migrations
    fi

    log_info "=== Migracoes concluidas ==="
}

main "$@"
