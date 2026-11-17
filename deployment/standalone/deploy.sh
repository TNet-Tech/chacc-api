#!/bin/bash
set -e

# ChaCC API - Standalone Deployment Script
# Installs (or upgrades) chacc-api on a Linux server as a systemd service.
# Safe to run again: an existing .env is kept, the package is upgraded.
#
# Optional settings (environment variables):
#   CHACC_PACKAGE  what pip installs (default: chacc-api; e.g. "chacc-api==1.0.0b6"
#                  or a path to a wheel)
#   PORT           port to listen on (default: 8085)

# Configuration
APP_NAME="chacc-api"
APP_DIR="/opt/chacc-api"
APP_USER="chacc-api"
VENV="$APP_DIR/.venv"
PORT="${PORT:-8085}"
CHACC_PACKAGE="${CHACC_PACKAGE:-chacc-api}"

# Folders the server writes to (relative to APP_DIR, ChaCC's defaults). If you move
# one in .env (MODULES_INSTALLED_DIR, MODULE_PACKAGES_DIR, ...), add it here too.
DATA_DIRS=".modules_installed .modules_loaded .modules_upload .chacc_cache .chacc_packages .dependency_cache backups plugins"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root"
    exit 1
fi

log_info "Starting $APP_NAME deployment..."

# Step 1: Install Python if needed
if ! command -v python3 &> /dev/null; then
    log_info "Installing Python..."
    if command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y python3 python3-venv python3-pip curl openssl
    elif command -v dnf &> /dev/null; then
        dnf install -y python3 python3-pip curl openssl
    elif command -v yum &> /dev/null; then
        yum install -y python3 python3-pip curl openssl
    elif command -v apk &> /dev/null; then
        apk add --no-cache python3 py3-pip curl openssl
    else
        log_error "Cannot install Python. Please install Python 3.10+ manually."
        exit 1
    fi
fi

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    log_error "Python 3.10+ is required (found $(python3 --version 2>&1))."
    exit 1
fi
if ! python3 -c 'import ensurepip, venv' &> /dev/null; then
    log_error "The Python venv module is missing. Install it (e.g. apt-get install python3-venv) and run again."
    exit 1
fi

# Step 2: Create user
log_info "Creating user..."
id -u "$APP_USER" &>/dev/null || useradd -r -s /bin/false -d "$APP_DIR" "$APP_USER"
mkdir -p "$APP_DIR"

# Step 3: Install the application (root-owned, so modules can't modify it)
log_info "Setting up virtual environment..."
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"

log_info "Installing $CHACC_PACKAGE..."
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install --upgrade "$CHACC_PACKAGE"

# Step 4: Configuration (kept if it already exists, so secrets survive re-runs)
if [ -f "$APP_DIR/.env" ]; then
    log_info "Keeping existing $APP_DIR/.env"
else
    log_info "Creating environment configuration..."
    cat > "$APP_DIR/.env" <<EOF
CHACC_DEV_MODE=false
DATABASE_ENGINE=postgresql
DATABASE_HOST=localhost
DATABASE_NAME=chacc
DATABASE_USER=chacc
DATABASE_PASSWORD=changeme
SECRET_KEY=$(openssl rand -hex 32)
ENABLE_PLUGIN_HOT_RELOAD=False
PLUGIN_AUTO_DISCOVERY=False
ENABLE_PLUGIN_DEPENDENCY_RESOLUTION=False
NO_RELOAD=True
LOG_LEVEL=INFO
EOF
    log_warn "Set DATABASE_PASSWORD (and the other database settings) in $APP_DIR/.env"
fi
chown "root:$APP_USER" "$APP_DIR/.env"
chmod 640 "$APP_DIR/.env"

# Reference copy of every setting (the server can't write it into APP_DIR itself)
"$VENV/bin/python" -c "from importlib.resources import files; print(files('chacc_api').joinpath('.env.sample').read_text(), end='')" \
    > "$APP_DIR/.env.sample" 2>/dev/null || rm -f "$APP_DIR/.env.sample"

# Step 5: Data folders, the only places the server can write
RW_PATHS=""
for dir in $DATA_DIRS; do
    mkdir -p "$APP_DIR/$dir"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR/$dir"
    RW_PATHS="$RW_PATHS $APP_DIR/$dir"
done

# Step 6: systemd service
log_info "Installing systemd service..."
cat > "/etc/systemd/system/${APP_NAME}.service" <<EOF
[Unit]
Description=ChaCC API - Modular FastAPI Platform
After=network-online.target postgresql.service
Wants=network-online.target postgresql.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment=PATH=$VENV/bin:/usr/local/bin:/usr/bin:/bin
Environment=CHACC_DEV_MODE=false
Environment=PIP_NO_CACHE_DIR=1
ExecStart=$VENV/bin/chacc run server --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=10

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$RW_PATHS

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$APP_NAME

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$APP_NAME"

log_info "Starting $APP_NAME..."
systemctl restart "$APP_NAME"

# Step 7: Wait for the health check (database migrations can take a moment)
HEALTH_URL="http://localhost:$PORT/api/health"
for _ in $(seq 1 60); do
    if python3 -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2)" "$HEALTH_URL" &> /dev/null; then
        log_info "Installation complete!"
        log_info "Access the API at http://localhost:$PORT"
        log_info "Health check: $HEALTH_URL"
        exit 0
    fi
    systemctl is-failed --quiet "$APP_NAME" && break
    sleep 1
done

log_error "Service did not become healthy. Check logs with: journalctl -u $APP_NAME -f"
exit 1
