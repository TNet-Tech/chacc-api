# Configuration

ChaCC API reads configuration through environment variables and `python-decouple`.
The packaged `.env.sample` can be copied to `.env` and customized.

## Model registration

Models that inherit from `ChaCCBaseModel` are discovered automatically through
SQLAlchemy's declarative `metadata_obj`. The legacy `@register_model` decorator
is retained as a backward-compatible no-op and should not be used in new code.

## Required production value

| Variable | Requirement |
| --- | --- |
| `SECRET_KEY` | Required in production, at least 32 characters, and must not match common insecure patterns such as `dev-`, `test-`, `default`, or repeated characters. |

## Access

| Variable | Default | Description |
| --- | --- | --- |
| `CHACC_CONSOLE_KEY` | empty | Key for the web console and the core `/modules` and `/system` routes when the authentication module isn't loaded. Any characters; at least 8 recommended (shorter only logs a warning). Empty: they are open, with a warning. See [Without the authentication module](console.md#without-the-authentication-module). |
| `CHACC_ADMIN_PRIVILEGE` | `MANAGE_WEB_CONSOLE` | Privilege for the web console and the core `/modules` and `/system` routes when the authentication module is loaded. Capital letters, digits and `_`; an empty or invalid value uses the default. `ALL` always has access. See [Who can use it](console.md#who-can-use-it). |

## Database

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_ENGINE` | `sqlite` | Use `sqlite` or `postgresql`. |
| `DATABASE_NAME` | `chaccapidb` | Database name. |
| `DATABASE_USER` | `chacc` | PostgreSQL username. |
| `DATABASE_PASSWORD` | empty | PostgreSQL password. |
| `DATABASE_HOST` | `localhost` | PostgreSQL host. |
| `DATABASE_PORT` | `5432` | PostgreSQL port. |

SQLite stores the database at `chaccapi.db` in the current working directory by default.

| Variable | Default | Description |
| --- | --- | --- |
| `SQLITE_DATABASE_NAME` | `chaccapi.db` | SQLite database file name. |
| `SQLITE_DATABASE_PATH` | Current working directory | Directory used for SQLite database storage. |

## Module directories

| Variable | Default | Description |
| --- | --- | --- |
| `API_PREFIX` | `/api` | Prefix for all core and module routes (empty for none). Exposed to clients at `GET /.well-known/chacc`. |
| `CHACC_GRACEFUL_SHUTDOWN_TIMEOUT` | `30` | Seconds in-flight requests get to finish on shutdown/restart. |
| `PLUGINS_DIR` | `plugins` | Directory for development modules. |
| `MODULES_INSTALLED_DIR` | `.modules_installed` | Directory containing `.chacc` archives. |
| `MODULES_LOADED_DIR` | `.modules_loaded` | Directory where archives are extracted. |
| `MODULES_UPLOAD_DIR` | `.modules_upload` | Temporary upload staging directory. |
| `DEPENDENCY_CACHE_DIR` | `.chacc_cache` | Dependency resolution cache. |
| `MODULE_PACKAGES_DIR` | `.chacc_packages` | Production: where Python packages that modules need are installed. Keep it on a volume. |
| `CHACC_BOOT_INSTALL` | `missing` | What startup may do about missing module packages: `missing` tries once to install them (needs network), `never` never calls pip. Modules whose packages are still missing are not loaded. |
| `CHACC_BOOT_INSTALL_TIMEOUT` | `120` | Seconds for that startup attempt. |

## Development settings

| Variable | Default | Description |
| --- | --- | --- |
| `CHACC_DEV_MODE` | `false` | Enables development-mode module loading. |
| `ENABLE_PLUGIN_HOT_RELOAD` | `false` | Development mode: restarts the server when files in `plugins/` change, and creates and migrates the plugins' tables. Off: neither, and only `src/` changes restart the server. Must be off in production. |
| `PLUGIN_AUTO_DISCOVERY` | `false` | Automatically discover plugins. |
| `ENABLE_PLUGIN_DEPENDENCY_RESOLUTION` | `false` | Development only: resolve and install plugin requirements into the active environment at startup. Production ignores it. |

## Migration settings

| Variable | Default | Description |
| --- | --- | --- |
| `MIGRATION_MODE` | `auto` | `preview`, `auto`, or `full`. |
| `MIGRATION_BACKUP` | `false` | Back up the database before a migration that changes it (`auto` and `full`). |
| `MIGRATION_BACKUP_DIR` | `backups` | Backup directory. |
| `MIGRATION_AUTO_DROP` | `false` | Present for deployment scripts; migration runner uses `auto` safe filtering. |
| `SQLITE_FOREIGN_KEYS` | `false` | SQLite only: enforce foreign keys. See [Foreign keys on SQLite](database-migrations.md#foreign-keys-on-sqlite). |

## Redis

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_ENABLED` | `false` | Enable Redis service registration. |
| `REDIS_HOST` | `localhost` | Redis host. |
| `REDIS_PORT` | `6379` | Redis port. |
| `REDIS_DB` | `0` | Redis database number. |
| `REDIS_PASSWORD` | empty | Redis password. |

## Rate limiting

These apply to every limit set with `chacc_api.rate_limit` (see
[Rate limiting](modules.md#rate-limiting)). Changes take effect after a restart.

| Variable | Default | Description |
| --- | --- | --- |
| `RATE_LIMIT_ENABLED` | `true` | `false` turns every limit off: no route answers `429`, and `check_rate_limit()` always allows. For load tests or debugging; keep `true` in production. |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | Where request counts are kept. See below. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1,::1` | Read by uvicorn. Addresses of reverse proxies whose `X-Forwarded-For` header gives the client IP. |

**Choosing the storage**

| Value | Counts are | Use when |
| --- | --- | --- |
| `memory://` | Kept in the server process, lost on restart. | One server. |
| `redis://[:password@]host:6379/0` | Shared by all servers, kept across restarts. | More than one server or container, or limits must survive restarts. |
| `rediss://[:password@]host:6380/0` | Same, over TLS. | Redis needs TLS. |

With `memory://` and several servers, each one allows the full limit, so clients
get several times the limit in total. `RATE_LIMIT_STORAGE_URI` is separate from the
`REDIS_*` settings, which don't configure it. If Redis can't be reached, the server
counts in memory and logs a warning, so requests keep working; it goes back to Redis
when it is reachable again. With Docker Compose, see
[Redis (optional)](deployment.md#redis-optional).

**Behind a reverse proxy**

Clients are counted by IP. Behind nginx, a load balancer or another proxy, the
server only sees the proxy's address, so every client shares one limit. Set
`FORWARDED_ALLOW_IPS` to the proxy's address (or several, comma-separated) and the
client IP is read from `X-Forwarded-For`. Don't use `*` when clients can also reach
the server directly: they could send their own `X-Forwarded-For` and pick any IP.

## CORS

| Variable | Default | Description |
| --- | --- | --- |
| `CORS_ALLOWED_ORIGINS` | `*` | Allowed origins. |
| `CORS_ALLOW_CREDENTIALS` | `true` | Allow credentials. |
| `CORS_ALLOW_METHODS` | `*` | Allowed methods. |
| `CORS_ALLOW_HEADERS` | `*` | Allowed headers. |

## CLI deployment

| Variable | Default | Description |
| --- | --- | --- |
| `CHACC_DEPLOY_URL` | `http://localhost:8085` | Remote ChaCC API base URL for `chacc deploy`. |
| `CHACC_DEPLOY_API_KEY` | empty | Optional bearer token for deployment. |
| `CHACC_DEPLOY_KEY` | empty | The server's `CHACC_CONSOLE_KEY`, for servers without the authentication module. Sent only when the server asks for it; prompted for when unset. |
| `CHACC_DEPLOY_USERNAME` | empty | Username for non-interactive login when the server returns 401. |
| `CHACC_DEPLOY_PASSWORD` | empty | Password for non-interactive login when the server returns 401. |
| `CHACC_DEPLOY_AUTH_PATH` | `/authentication` | Authentication module's `base_path_prefix` (the API prefix is added automatically). |
| `CHACC_DEPLOY_API_PREFIX` | discovered | Override the server's API prefix. Unset: read from `GET /.well-known/chacc`, falling back to `/api`. Empty: no prefix. |
| `CHACC_DEPLOY_RESTART_TIMEOUT` | `180` | Seconds `chacc deploy --restart` waits for the server to come back. |
| `CHACC_DEPLOY_TIMEOUT` | `600` | Seconds to wait for the server response after upload. |

## Module-specific configuration

Modules can read environment variables through `BackboneContext`.

```python
value = context.get_module_config("api_key", "billing")
```

This checks:

1. `BILLING_API_KEY`
2. `API_KEY`
3. The provided default value, if given

Use uppercase names in `.env`:

```bash
BILLING_API_KEY=sk_live_example
BILLING_SECRET=replace-me
```

## Logging

| Variable | Default | Description |
| --- | --- | --- |
| `CHACC_VERBOSE` | `false` | Enables `INFO` logging when true. |
| `CHACC_DEBUG` | `false` | Enables `DEBUG` logging when true. |

Default log level behavior:

- Neither `CHACC_VERBOSE` nor `CHACC_DEBUG` set: `WARNING`.
- `CHACC_VERBOSE=true`: `INFO`.
- `CHACC_DEBUG=true`: `DEBUG`.

Alembic logs are suppressed to `WARNING`.

## Production validation

In production mode, ChaCC API validates:

- `SECRET_KEY` is present and strong.
- PostgreSQL configuration includes host, user, password, and database name.
- Hot reload is disabled.
- Plugin auto-discovery is disabled.

Development mode logs warnings for development-only settings that should be
disabled in production.
