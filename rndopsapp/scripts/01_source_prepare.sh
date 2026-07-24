#!/bin/bash
###############################################################################
# 01_source_prepare.sh — Run on SOURCE server (172.14.131.57)
#
# Creates a backup of the Frappe site and transfers it to the target server.
# Also zips all custom/private apps for transfer.
#
# Usage:
#   chmod +x 01_source_prepare.sh
#   ./01_source_prepare.sh
###############################################################################

set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

# ─────────────────────── Configuration ───────────────────────
SOURCE_BENCH="$HOME/frappe-dev/prornd"
SITE_NAME="prornd.local"
TARGET_USER="iitg_oc_2025"
TARGET_IP="172.16.134.191"
TARGET_DIR="/home/${TARGET_USER}/frappe_transfer"

# Apps to zip and transfer (private/custom apps not on public GitHub)
CUSTOM_APPS=("rndopsapp")

# ─────────────────────── Colors ───────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ─────────────────────── Preflight Checks ───────────────────────
info "=== Source Server Preparation Script ==="
info "Source bench: ${SOURCE_BENCH}"
info "Target: ${TARGET_USER}@${TARGET_IP}"

cd "${SOURCE_BENCH}" || error "Bench directory not found: ${SOURCE_BENCH}"

# ─────────────────────── Step 1: Backup Site ───────────────────────
info "Step 1: Creating site backup with files..."
bench --site "${SITE_NAME}" backup --with-files

# Find the latest backup files
BACKUP_DIR="${SOURCE_BENCH}/sites/${SITE_NAME}/private/backups"
LATEST_DB=$(ls -t "${BACKUP_DIR}"/*-database.sql.gz 2>/dev/null | head -1)
#LATEST_PUB=$(ls -t "${BACKUP_DIR}"/*-files.tar 2>/dev/null | head -1)
LATEST_PUB=$(ls -t "${BACKUP_DIR}"/*-files.tar 2>/dev/null | grep -v "private-files.tar" | head -1)
LATEST_PRIV=$(ls -t "${BACKUP_DIR}"/*-private-files.tar 2>/dev/null | head -1)
LATEST_CONFIG=$(ls -t "${BACKUP_DIR}"/*-site_config_backup.json 2>/dev/null | head -1)

[ -z "${LATEST_DB}" ] && error "Database backup not found!"
[ -z "${LATEST_PUB}" ] && error "Public files backup not found!"
[ -z "${LATEST_PRIV}" ] && error "Private files backup not found!"

TIMESTAMP=$(basename "${LATEST_DB}" | cut -d'-' -f1)
info "Backup timestamp: ${TIMESTAMP}"
info "  Database:      $(basename ${LATEST_DB}) ($(du -h ${LATEST_DB} | cut -f1))"
info "  Public files:  $(basename ${LATEST_PUB}) ($(du -h ${LATEST_PUB} | cut -f1))"
info "  Private files: $(basename ${LATEST_PRIV}) ($(du -h ${LATEST_PRIV} | cut -f1))"

# ─────────────────────── Step 2: Zip Custom Apps ───────────────────────
info "Step 2: Zipping custom apps..."
STAGING_DIR="/tmp/frappe_transfer_$$"
mkdir -p "${STAGING_DIR}"

for app in "${CUSTOM_APPS[@]}"; do
    APP_PATH="${SOURCE_BENCH}/apps/${app}"
    if [ -d "${APP_PATH}" ]; then
        info "  Zipping ${app}..."
        cd "${SOURCE_BENCH}/apps"
        zip -rq "${STAGING_DIR}/${app}.zip" "${app}" \
            -x "${app}/.git/*" "${app}/node_modules/*" "*/__pycache__/*" "*.pyc" "*.pyo"
        info "  Created: ${app}.zip ($(du -h ${STAGING_DIR}/${app}.zip | cut -f1))"
    else
        warn "  App folder not found: ${APP_PATH}, skipping..."
    fi
done

# Copy backup files to staging
cp "${LATEST_DB}" "${LATEST_PUB}" "${LATEST_PRIV}" "${STAGING_DIR}/"
[ -n "${LATEST_CONFIG}" ] && cp "${LATEST_CONFIG}" "${STAGING_DIR}/"

# Save app versions for reference
cd "${SOURCE_BENCH}"
bench version > "${STAGING_DIR}/app_versions.txt" 2>/dev/null || true

# ─────────────────────── Step 3: Transfer to Target ───────────────────────
info "Step 3: Transferring files to target server..."
info "  Creating target directory..."
ssh "${TARGET_USER}@${TARGET_IP}" "mkdir -p ${TARGET_DIR}"

info "  Transferring backup files and app zips..."
scp -r "${STAGING_DIR}/"* "${TARGET_USER}@${TARGET_IP}:${TARGET_DIR}/"

# ─────────────────────── Step 4: Cleanup ───────────────────────
info "Step 4: Cleaning up staging directory..."
rm -rf "${STAGING_DIR}"

# ─────────────────────── Summary ───────────────────────
echo ""
info "============================================="
info " SOURCE PREPARATION COMPLETE"
info "============================================="
info ""
info "Files transferred to ${TARGET_USER}@${TARGET_IP}:${TARGET_DIR}/"
info ""
info "Next: SSH into the target server and run:"
info "  ssh ${TARGET_USER}@${TARGET_IP}"
info "  chmod +x ~/02_target_install.sh"
info "  ./02_target_install.sh"
info ""
info "Backup timestamp: ${TIMESTAMP}"
info "============================================="
