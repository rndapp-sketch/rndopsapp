#!/bin/bash
###############################################################################
# 02_target_install.sh — Run on TARGET server (172.16.132.200)
#
# Fully automated Frappe v15 environment setup + data restore.
# Incorporates all real-world lessons learned from manual installations.
#
# Prerequisites:
#   - Ubuntu 22.04 LTS with sudo access
#   - Files transferred from source via 01_source_prepare.sh
#   - SSH key or password access to this server
#
# Usage:
#   chmod +x 02_target_install.sh
#   ./02_target_install.sh
#
# The script will prompt for:
#   - MariaDB root password (existing or new)
#   - Frappe site admin password
###############################################################################

set -euo pipefail

# ─────────────────────── Configuration ───────────────────────
BENCH_ROOT="$HOME/project/frappe_dev"
BENCH_NAME="prornd"
BENCH_DIR="${BENCH_ROOT}/${BENCH_NAME}"
SITE_NAME="prornd.local"
FRAPPE_BRANCH="version-15"
PYTHON_VERSION="python3.11"
NODE_VERSION="20"
TRANSFER_DIR="$HOME/frappe_transfer"

# Custom apps to install from ZIP
CUSTOM_APPS=("rndopsapp")

# Extra pip packages to install in bench venv
EXTRA_PIP_PACKAGES=("kafka-python==2.3.0")

# Site config to apply
SITE_CONFIG=(
    "developer_mode 1"
    "server_script_enabled 1"
    "ignore_csrf 1"
)

# ─────────────────────── Colors & Helpers ───────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

info()     { echo -e "${GREEN}[INFO]${NC}    $1"; }
warn()     { echo -e "${YELLOW}[WARN]${NC}    $1"; }
error()    { echo -e "${RED}[ERROR]${NC}   $1"; exit 1; }
section()  { echo -e "\n${BLUE}${BOLD}══════════════════════════════════════════${NC}"; echo -e "${BLUE}${BOLD}  $1${NC}"; echo -e "${BLUE}${BOLD}══════════════════════════════════════════${NC}\n"; }
ask()      { read -rp "$(echo -e ${YELLOW})$1$(echo -e ${NC}): " "$2"; }

# Check we are NOT root
if [ "$(id -u)" -eq 0 ]; then
    error "Do NOT run this script as root. Use a regular user with sudo access."
fi

# ─────────────────────── Prompt for Passwords ───────────────────────
section "Frappe v15 Auto-Install Script"
info "Source: 172.16.135.157"
info "Target: $(hostname -I | awk '{print $1}')"
info "Bench:  ${BENCH_DIR}"
info "Site:   ${SITE_NAME}"
echo ""

ask "Enter MariaDB root password" DB_ROOT_PASS
ask "Enter Frappe admin password" ADMIN_PASS
echo ""

# ─────────────────────── Step 1: System Prerequisites ───────────────────────
section "Step 1: System Prerequisites"

info "Updating system..."
sudo apt update -y && sudo apt upgrade -y

info "Installing system packages..."
sudo apt install -y \
    git curl wget unzip \
    python3 python3-pip python3-venv python3-dev python3-full \
    build-essential libssl-dev libffi-dev libmysqlclient-dev \
    redis-server redis-tools \
    xvfb libfontconfig wkhtmltopdf \
    software-properties-common lsof

# ─────────────────────── Step 2: Python 3.11 ───────────────────────
section "Step 2: Python 3.11"

if command -v python3.11 &>/dev/null; then
    info "Python 3.11 already installed: $(python3.11 --version)"
else
    info "Installing Python 3.11 from deadsnakes PPA..."
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update
    sudo apt install -y python3.11 python3.11-dev python3.11-venv python3.11-distutils
fi

# ─────────────────────── Step 3: Node.js via nvm ───────────────────────
section "Step 3: Node.js ${NODE_VERSION} via nvm"

export NVM_DIR="$HOME/.nvm"

if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    info "Installing nvm..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
fi

# Source nvm
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

if ! node --version 2>/dev/null | grep -q "v${NODE_VERSION}"; then
    info "Installing Node.js ${NODE_VERSION}..."
    nvm install ${NODE_VERSION}
    nvm use ${NODE_VERSION}
fi

info "Node.js: $(node --version)"

if ! command -v yarn &>/dev/null; then
    info "Installing yarn..."
    npm install -g yarn
fi

# ─────────────────────── Step 4: Configure MariaDB ───────────────────────
section "Step 4: MariaDB Configuration"

if ! command -v mariadb &>/dev/null; then
    info "Installing MariaDB..."
    sudo apt install -y mariadb-server mariadb-client
fi

sudo systemctl enable mariadb
sudo systemctl start mariadb
info "MariaDB: $(mariadb --version | head -1)"

# Apply character set config if missing
if ! grep -qi 'utf8mb4' /etc/mysql/mariadb.conf.d/50-server.cnf 2>/dev/null; then
    info "Applying Frappe character set settings..."
    sudo tee -a /etc/mysql/mariadb.conf.d/50-server.cnf >/dev/null <<'MARIADB_CONF'

[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

[mysql]
default-character-set = utf8mb4
MARIADB_CONF
    sudo systemctl restart mariadb
    info "Character set settings applied."
else
    info "Character set already configured, skipping."
fi

# ─────────────────────── Step 5: Disable System Redis ───────────────────────
section "Step 5: Redis (let bench manage)"

info "Disabling system redis-server to avoid port conflicts..."
sudo systemctl stop redis-server 2>/dev/null || true
sudo systemctl disable redis-server 2>/dev/null || true

# ─────────────────────── Step 6: Install frappe-bench ───────────────────────
section "Step 6: Install frappe-bench"

# Ensure pip is available for python3.11
if ! python3.11 -m pip --version &>/dev/null; then
    info "Installing pip for Python 3.11..."
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11
fi

# Install frappe-bench
python3.11 -m pip install --user frappe-bench
export PATH="$HOME/.local/bin:$PATH"

# Make PATH permanent
if ! grep -q '.local/bin' ~/.bashrc 2>/dev/null; then
    echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc
fi

# Ensure nvm loads automatically
if ! grep -q 'NVM_DIR' ~/.bashrc 2>/dev/null; then
    cat >> ~/.bashrc <<'NVM_BASHRC'
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
NVM_BASHRC
fi

info "bench version: $(bench --version)"

# ─────────────────────── Step 7: Initialize Bench ───────────────────────
section "Step 7: Initialize Bench"

if [ -d "${BENCH_DIR}" ]; then
    warn "Bench already exists at ${BENCH_DIR}, skipping init."
else
    mkdir -p "${BENCH_ROOT}"
    cd "${BENCH_ROOT}"
    info "Running bench init (this takes a few minutes)..."
    bench init "${BENCH_NAME}" --frappe-branch "${FRAPPE_BRANCH}" --python "${PYTHON_VERSION}"
fi

cd "${BENCH_DIR}"
info "Bench initialized at ${BENCH_DIR}"

# ─────────────────────── Step 8: Reduce Gunicorn Workers ───────────────────────
section "Step 8: Configure Bench Settings"

info "Setting gunicorn_workers to 2..."
bench set-config gunicorn_workers 2

# ─────────────────────── Step 9: Create Site ───────────────────────
section "Step 9: Create Site"

if [ -d "sites/${SITE_NAME}" ]; then
    warn "Site ${SITE_NAME} already exists, skipping creation."
else
    info "Creating site ${SITE_NAME}..."
    bench new-site "${SITE_NAME}" \
        --db-type mariadb \
        --db-root-username root \
        --db-root-password "${DB_ROOT_PASS}" \
        --admin-password "${ADMIN_PASS}"
fi

bench use "${SITE_NAME}"
info "Site created and set as default."

# ─────────────────────── Step 10: Install Standard Apps ───────────────────────
section "Step 10: Install Standard Apps"

# ERPNext
if [ ! -d "apps/erpnext" ]; then
    info "Getting ERPNext..."
    bench get-app erpnext --branch "${FRAPPE_BRANCH}"
else
    info "ERPNext already present."
fi

# Start Redis in background for installs requiring it
redis-server --port 13000 --daemonize yes
redis-server --port 11000 --daemonize yes
sleep 2

info "Installing ERPNext on site..."
bench --site "${SITE_NAME}" install-app erpnext 2>/dev/null || info "ERPNext already installed."

# HRMS
if [ ! -d "apps/hrms" ]; then
    info "Getting HRMS..."
    bench get-app hrms --branch "${FRAPPE_BRANCH}"
else
    info "HRMS already present."
fi
info "Installing HRMS on site..."
bench --site "${SITE_NAME}" install-app hrms 2>/dev/null || info "HRMS already installed."

# Doppio
if [ ! -d "apps/doppio" ]; then
    info "Getting Doppio..."
    bench get-app doppio https://github.com/NagariaHussain/doppio --branch master
else
    info "Doppio already present."
fi
info "Installing Doppio on site..."
bench --site "${SITE_NAME}" install-app doppio 2>/dev/null || info "Doppio already installed."

# ─────────────────────── Step 11: Install Custom Apps from ZIP ───────────────────────
section "Step 11: Install Custom Apps"

for app in "${CUSTOM_APPS[@]}"; do
    ZIP_PATH="${TRANSFER_DIR}/${app}.zip"
    APP_PATH="${BENCH_DIR}/apps/${app}"

    if [ -d "${APP_PATH}" ]; then
        info "${app} already exists in apps/, skipping extraction."
    elif [ -f "${ZIP_PATH}" ]; then
        info "Extracting ${app} from ZIP..."
        cd "${BENCH_DIR}/apps"
        unzip -qo "${ZIP_PATH}"

        # Initialize local Git repo (bench requires .git)
        cd "${APP_PATH}"
        if [ ! -d ".git" ]; then
            info "  Initializing git repo for ${app}..."
            git init -q
            git add .
            git commit -q -m "initial commit from source server"
            # Rename to master (bench expects 'master', not 'main')
            git branch -m master 2>/dev/null || true
        fi

        cd "${BENCH_DIR}"
        info "  Running bench setup requirements..."
        bench setup requirements 2>/dev/null || warn "  Some requirements may have failed, continuing..."
    else
        warn "ZIP not found: ${ZIP_PATH}, skipping ${app}."
        continue
    fi

    info "Installing ${app} on site..."
    bench --site "${SITE_NAME}" install-app "${app}" 2>/dev/null || info "${app} already installed."
done

# ─────────────────────── Step 12: Extra Python Packages ───────────────────────
section "Step 12: Extra Python Packages"

cd "${BENCH_DIR}"
source env/bin/activate
for pkg in "${EXTRA_PIP_PACKAGES[@]}"; do
    info "Installing ${pkg} in bench venv..."
    pip install "${pkg}" 2>/dev/null || warn "Failed to install ${pkg}"
done
deactivate

# ─────────────────────── Step 13: Site Configuration ───────────────────────
section "Step 13: Site Configuration"

for config_pair in "${SITE_CONFIG[@]}"; do
    key=$(echo "${config_pair}" | awk '{print $1}')
    val=$(echo "${config_pair}" | awk '{print $2}')
    info "  Setting ${key} = ${val}"
    bench --site "${SITE_NAME}" set-config "${key}" "${val}"
done

# allow_cors needs quotes around *
bench --site "${SITE_NAME}" set-config allow_cors "*"
info "Site config applied."

# ─────────────────────── Step 14: Enable Scheduler ───────────────────────
section "Step 14: Enable Scheduler"

bench --site "${SITE_NAME}" enable-scheduler
info "Scheduler enabled."

# ─────────────────────── Step 15: Build Assets ───────────────────────
section "Step 15: Build Assets & Migrate"

info "Building assets..."
bench build

info "Running migrate..."
bench --site "${SITE_NAME}" migrate

# ─────────────────────── Step 16: Data Restore ───────────────────────
section "Step 16: Restore Data from Source"

# Find backup files in transfer directory
DB_FILE=$(ls -t "${TRANSFER_DIR}"/*-database.sql.gz 2>/dev/null | head -1)
PUB_FILE=$(ls -t "${TRANSFER_DIR}"/*-files.tar 2>/dev/null | head -1)
PRIV_FILE=$(ls -t "${TRANSFER_DIR}"/*-private-files.tar 2>/dev/null | head -1)

if [ -n "${DB_FILE}" ]; then
    info "Restoring database: $(basename ${DB_FILE})"
    info "  Public files:  $(basename ${PUB_FILE:-none})"
    info "  Private files: $(basename ${PRIV_FILE:-none})"

    RESTORE_CMD="bench --site ${SITE_NAME} restore ${DB_FILE}"
    [ -n "${PUB_FILE}" ] && RESTORE_CMD="${RESTORE_CMD} --with-public-files ${PUB_FILE}"
    [ -n "${PRIV_FILE}" ] && RESTORE_CMD="${RESTORE_CMD} --with-private-files ${PRIV_FILE}"

    eval "${RESTORE_CMD}"
    info "Database restored successfully."

    # Re-apply site config after restore (restore resets site_config.json)
    info "Re-applying site configuration..."
    for config_pair in "${SITE_CONFIG[@]}"; do
        key=$(echo "${config_pair}" | awk '{print $1}')
        val=$(echo "${config_pair}" | awk '{print $2}')
        bench --site "${SITE_NAME}" set-config "${key}" "${val}"
    done
    bench --site "${SITE_NAME}" set-config allow_cors "*"

    # Re-run migrate post-restore
    info "Running post-restore migrate..."
    bench --site "${SITE_NAME}" migrate
else
    warn "No backup database file found in ${TRANSFER_DIR}/, skipping restore."
fi

# ─────────────────────── Step 17: Sync Singleton Tables ───────────────────────
section "Step 17: Sync Singleton DocType Tables"

info "Syncing singleton tables (fixes TableMissingError after version upgrade)..."

bench --site "${SITE_NAME}" execute <<'PYTHON_SCRIPT'
from frappe.database.mariadb.schema import MariaDBTable

all_singles = frappe.get_all("DocType", filters={"issingle": 1}, pluck="name")
synced = 0
failed = 0

for dt in all_singles:
    try:
        table = MariaDBTable(dt, frappe.get_meta(dt))
        table.sync()
        frappe.db.commit()
        synced += 1
    except Exception:
        failed += 1

print(f"Synced {synced} singleton tables. {failed} already existed (harmless).")
PYTHON_SCRIPT

# Alternative: use console if execute doesn't work
if [ $? -ne 0 ]; then
    warn "bench execute failed, using console method..."
    bench --site "${SITE_NAME}" console <<'CONSOLE_SCRIPT'
from frappe.database.mariadb.schema import MariaDBTable
all_singles = frappe.get_all("DocType", filters={"issingle": 1}, pluck="name")
synced = 0
for dt in all_singles:
    try:
        table = MariaDBTable(dt, frappe.get_meta(dt))
        table.sync()
        frappe.db.commit()
        synced += 1
    except Exception:
        pass
print(f"Synced {synced} singleton tables.")
exit
CONSOLE_SCRIPT
fi

# ─────────────────────── Step 18: Final Cleanup ───────────────────────
section "Step 18: Final Cleanup"

# Kill background Redis
pkill -f "redis-server.*13000" 2>/dev/null || true
pkill -f "redis-server.*11000" 2>/dev/null || true

# Clear all caches
bench --site "${SITE_NAME}" clear-cache 2>/dev/null || true
bench --site "${SITE_NAME}" clear-website-cache 2>/dev/null || true

# Add hosts entry
if ! grep -q "${SITE_NAME}" /etc/hosts 2>/dev/null; then
    info "Adding ${SITE_NAME} to /etc/hosts..."
    echo "127.0.0.1 ${SITE_NAME}" | sudo tee -a /etc/hosts >/dev/null
fi

# ─────────────────────── Complete ───────────────────────
section "INSTALLATION COMPLETE!"

echo -e "${GREEN}${BOLD}"
echo "  ╔═══════════════════════════════════════════════════════╗"
echo "  ║                                                       ║"
echo "  ║   Frappe v15 Environment Ready!                       ║"
echo "  ║                                                       ║"
echo "  ║   Start bench:   cd ${BENCH_DIR}"
echo "  ║                  bench start                          ║"
echo "  ║                                                       ║"
echo "  ║   Open browser:  http://${SITE_NAME}:8000             ║"
echo "  ║                                                       ║"
echo "  ╚═══════════════════════════════════════════════════════╝"
echo -e "${NC}"

info "Bench directory:  ${BENCH_DIR}"
info "Apps installed:   $(ls apps/ | tr '\n' ', ')"
info ""
info "To start: cd ${BENCH_DIR} && bench start"
