#!/bin/sh
set -e

# Data directories, resolved by ChaCC itself so custom locations work
# (MODULES_INSTALLED_DIR, MODULE_PACKAGES_DIR, DEPENDENCY_CACHE_DIR, ... set as
# environment variables or in .env). The same snippet points Python at the
# configured packages directory (after site-packages, so core packages win).
# Falls back to the defaults if ChaCC can't be imported.
DATA_DIRS=$(python - <<'EOF' 2>/dev/null || true
import os, site
from src import constants as c

dirs = [
    c.MODULES_INSTALLED_DIR, c.MODULES_LOADED_DIR, c.MODULES_UPLOAD_DIR,
    c.DEPENDENCY_CACHE_DIR, c.MODULE_PACKAGES_DIR, c.MIGRATION_BACKUP_DIR, c.PLUGINS_DIR,
]
if "postgres" not in c.DATABASE_ENGINE.lower():
    dirs.append(os.path.dirname(c.SQLITE_DB_PATH))

with open(os.path.join(site.getsitepackages()[0], "chacc_modules.pth"), "w") as f:
    f.write(c.MODULE_PACKAGES_DIR + "\n")

print("\n".join(dict.fromkeys(dirs)))
EOF
)
if [ -z "$DATA_DIRS" ]; then
    echo "docker-entrypoint: could not read ChaCC settings, using default directories" >&2
    DATA_DIRS="/app/.modules_installed
/app/.modules_loaded
/app/.modules_upload
/app/.chacc_cache
/app/.chacc_packages
/app/backups
/app/plugins"
fi

# Create them (fresh volumes are empty) and give them to the server user, also when
# they live outside /app. Only the server user can write there.
echo "$DATA_DIRS" | while IFS= read -r dir; do
    [ -n "$dir" ] || continue
    mkdir -p "$dir"
    chown -R chacc:chacc "$dir"
done

# Safety net: ensure the default home directory is writable too.
# Some tools (e.g. pip/pip-tools) resolve ~ from /etc/passwd, not $HOME.
mkdir -p /home/chacc && chown -R chacc:chacc /home/chacc

# No dependency resolution here. The server checks module packages itself at boot,
# as the chacc user: packages already in the packages directory (a volume) are used
# as they are, so restarts and recreated containers need no network. See
# `chacc deps check` / `chacc deps sync`.

# Chown everything under /app to the chacc user.
# Any new volume mounted under /app is automatically picked up — no script edits needed.
chown -R chacc:chacc /app

# Re-lock application code so modules can't overwrite it.
# This runs after the broad chown, so source stays root-owned.
chown -R root:root \
    /app/src \
    /app/chacc_api \
    /app/chacc_cli \
    /app/main.py \
    /app/deployment \
    /app/tests \
    /app/pyproject.toml \
    /app/requirements.txt \
    /app/requirements.lock \
    /app/setup.py 2>/dev/null || true

# Drop privileges and execute the original command
exec gosu chacc "$@"
