FROM python:3.15.2-slim

WORKDIR /app

# postgresql-client: pg_dump for MIGRATION_BACKUP=true on PostgreSQL (servers up to its version).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gosu \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r chacc && useradd -r -g chacc -d /app chacc

RUN mkdir -p /app/plugins /app/.modules_loaded /app/.modules_installed /app/.modules_upload /app/.chacc_cache /app/.chacc_packages /app/backups

COPY . /app/

# Core packages at the tested versions from requirements.lock.
RUN pip install --no-cache-dir -c requirements.lock chacc-api

# Module packages live in /app/.chacc_packages (a volume), after site-packages on sys.path,
# so they survive recreated containers and can never replace core packages.
RUN python -c "import os, site; open(os.path.join(site.getsitepackages()[0], 'chacc_modules.pth'), 'w').write('/app/.chacc_packages\n')"

COPY deployment/docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]

# PIP_USER=0 / PYTHONNOUSERSITE=1: never fall back to (or read) a per-user site-packages,
# which lives in the container layer and is lost when the container is recreated.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/app \
    PIP_USER=0 \
    PYTHONNOUSERSITE=1 \
    MODULE_PACKAGES_DIR=.chacc_packages \
    CHACC_DEV_MODE=false \
    ENABLE_PLUGIN_HOT_RELOAD=False \
    PLUGIN_AUTO_DISCOVERY=False \
    ENABLE_PLUGIN_DEPENDENCY_RESOLUTION=False

EXPOSE 8085

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; p = '/' + os.environ.get('API_PREFIX', '/api').strip('/'); urllib.request.urlopen('http://localhost:8085' + p.rstrip('/') + '/health')" || exit 1

CMD ["chacc", "run", "server"]
