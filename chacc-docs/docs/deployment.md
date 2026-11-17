# Deployment

ChaCC API can run as a Docker container, as part of Docker Compose, or as a
standalone Linux service.

## Docker

Build and run a local image:

```bash
docker run -d -p 8085:8085 chacc-api:latest
```

The Docker image installs `chacc-api` from PyPI and starts the server with:

```bash
chacc run server
```

## Docker Compose

Use the production compose file included in the repository:

```bash
docker compose -f deployment/docker/docker-compose.yml up -d
```

The compose stack includes:

- ChaCC API on port `8085`.
- PostgreSQL 16.
- Persistent PostgreSQL data volume.
- Persistent module storage volumes.
- Health checks for API and database readiness.
- Redis, optional (see below).

### Redis (optional)

ChaCC runs without Redis. Add it when:

- you run more than one ChaCC container, so rate limits are counted together
  instead of once per container;
- rate-limit counts should survive restarts;
- a module uses Redis (for example the outbound module's send limits).

The compose file includes a Redis service that only starts with the `redis`
profile. Set in `.env`:

```bash
REDIS_ENABLED=true
REDIS_HOST=redis
RATE_LIMIT_STORAGE_URI=redis://redis:6379/0
```

and start with:

```bash
docker compose -f deployment/docker/docker-compose.yml --profile redis up -d
```

ChaCC then waits for Redis before it starts. Redis data is kept in the
`redis_data` volume. To use a password, add `--requirepass <password>` to the
Redis `command` and use `REDIS_PASSWORD=<password>` and
`redis://:<password>@redis:6379/0`. To use a Redis you already run, skip the
profile and point `REDIS_HOST` and `RATE_LIMIT_STORAGE_URI` at it. See
[Rate limiting](configuration.md#rate-limiting) for what each setting does.

Health check calls:

```bash
curl http://localhost:8085/api/health
```

Example environment:

```bash
DB_PASSWORD=change-me
SECRET_KEY=replace-with-a-strong-random-secret
ADMIN_PASSWORD=replace-with-a-strong-admin-password
```

### Development

`docker-compose.dev.yml` runs `chacc run server --dev` with SQLite and your
working copy mounted. It works on its own:

```bash
docker compose -f deployment/docker/docker-compose.dev.yml up --build
```

Changes in `src/` reload the server. Changes in `chacc_api/` or `chacc_cli/` apply
after `docker compose -f deployment/docker/docker-compose.dev.yml restart`.
Modules are loaded from `plugins/`.

The server runs as your user (ID 1000 by default) so it can read the mounted
files. If `id -u` shows another ID, build with
`CHACC_UID=$(id -u) CHACC_GID=$(id -g) docker compose -f deployment/docker/docker-compose.dev.yml up --build`.

## Standalone Linux deployment

A deployment script is provided at `deployment/standalone/deploy.sh`.

```bash
sudo bash deployment/standalone/deploy.sh
```

The script:

1. Installs Python 3 if needed (3.10 or newer is required).
2. Creates the `chacc-api` user.
3. Installs `chacc-api` from PyPI into `/opt/chacc-api/.venv`, owned by root so modules can't change it.
4. Writes a production `.env` file, only if there isn't one yet. Set the database settings in it.
5. Creates the data folders. They are the only places the service can write.
6. Installs and starts a systemd service, then waits for the health check.

Run it again to upgrade: `.env` and your data are kept. Set `PORT` (default `8085`) or
`CHACC_PACKAGE` (for example `chacc-api==1.0.0b6`) before running it to change them. If you
move a data folder in `.env`, add it to `DATA_DIRS` in the script so the service can write there.

Access the API at:

```text
http://localhost:8085
```

Check service logs:

```bash
journalctl -u chacc-api -f
```

## Restarting after module changes

Use `chacc deploy my_module.chacc --restart`. The container keeps running. See
[Automatic Restarts](server-restarts.md#docker).

## Health checks

| Endpoint | Use |
| --- | --- |
| `/api/health` | Basic service health. |
| `/api/health/ready` | Readiness including database connectivity. |
| `/api/health/live` | Lightweight process liveness. |

Container health checks can call:

```bash
python -c "import urllib.request; urllib.request.urlopen('http://localhost:8085/api/health')"
```

## Production environment

Recommended production settings:

```bash
CHACC_DEV_MODE=false
DATABASE_ENGINE=postgresql
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_USER=chacc
DATABASE_NAME=chacc
DATABASE_PASSWORD=<strong-password>
SECRET_KEY=<random-32-plus-character-secret>
ENABLE_PLUGIN_HOT_RELOAD=false
PLUGIN_AUTO_DISCOVERY=false
ENABLE_PLUGIN_DEPENDENCY_RESOLUTION=false
MIGRATION_MODE=auto
MIGRATION_BACKUP=true
MIGRATION_BACKUP_DIR=backups
CHACC_VERBOSE=false
CHACC_DEBUG=false
```

## Module persistence

In containerized deployments, persist these directories if modules are installed
at runtime:

| Directory | Holds |
| --- | --- |
| `.modules_installed/` | Installed `.chacc` archives. |
| `.chacc_packages/` | Python packages that modules need. |
| `.chacc_cache/` | Resolved package versions and the last startup check. |
| `.modules_loaded/` | Extracted module code (rebuilt from the archives if lost). |
| `backups/` | Migration backups. |

The compose file mounts all of them except `.modules_loaded/`. Without
persistence, installed modules and their packages are lost when the container is
recreated.

Each directory can be moved with its variable (`MODULES_INSTALLED_DIR`,
`MODULE_PACKAGES_DIR`, `DEPENDENCY_CACHE_DIR`, ...; see
[Configuration](configuration.md)). Relative paths are under `/app`, absolute
paths are used as they are. The container creates the directories at startup and
makes them writable only by the server's user, so mount your volume at the new
path:

```yaml
environment:
  - MODULE_PACKAGES_DIR=/srv/chacc/packages
volumes:
  - chacc_packages:/srv/chacc/packages
```

## Running without network

Module packages are installed once, when a module is uploaded or enabled. After
that the server starts without network: restarts, `docker restart`, recreated
containers and new images on the same Python version all reuse
`.chacc_packages/`. Core packages are never replaced by a module.

Network is needed only to:

- upload or enable a module that needs new packages (the upload fails with 503
  and nothing changes when the package index can't be reached);
- start after a module was added without the API, for example by copying an
  archive into `.modules_installed/`.

If a module's packages are missing at startup, the server tries once to install
them, then starts without that module (and the modules that require it). The
console's dependency graph shows why. Set `CHACC_BOOT_INSTALL=never` to stop startup from ever
calling pip.

Check or repair the packages from the command line. In Docker, run it as the
server's user:

```bash
docker exec -u chacc chacc-api chacc deps check   # no network
docker exec -u chacc chacc-api chacc deps sync    # installs what is missing
```

!!! note "Changing the Python version"
    Packages in `.chacc_packages/` belong to one Python version. The images use
    Python 3.15. After an image with a different Python version, modules with
    compiled packages are not loaded until you run `chacc deps sync` with network.
