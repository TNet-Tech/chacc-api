#!/bin/sh
set -e

# Ensure data directories exist (handles fresh volumes that have no content yet).
# Volumes mounted by Docker are empty directories — the mount point exists but
# has no files. Creating the directory tree here guarantees the app can use them.
for dir in \
    /app/.modules_installed \
    /app/.modules_loaded \
    /app/.modules_upload \
    /app/.chacc_cache \
    /app/backups \
    /app/plugins; do
    mkdir -p "$dir"
done

# Safety net: ensure the default home directory is writable too.
# Some tools (e.g. pip/pip-tools) resolve ~ from /etc/passwd, not $HOME.
mkdir -p /home/chacc && chown -R chacc:chacc /home/chacc

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
    /app/setup.py 2>/dev/null || true

# Drop privileges and execute the original command
exec gosu chacc "$@"