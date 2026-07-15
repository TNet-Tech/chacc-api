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
| `PLUGINS_DIR` | `plugins` | Directory for development modules. |
| `MODULES_INSTALLED_DIR` | `.modules_installed` | Directory containing `.chacc` archives. |
| `MODULES_LOADED_DIR` | `.modules_loaded` | Directory where archives are extracted. |
| `MODULES_UPLOAD_DIR` | `.modules_upload` | Temporary upload staging directory. |
| `DEPENDENCY_CACHE_DIR` | `.chacc_cache` | Dependency resolution cache. |

## Development settings

| Variable | Default | Description |
| --- | --- | --- |
| `CHACC_DEV_MODE` | `false` | Enables development-mode module loading. |
| `ENABLE_PLUGIN_HOT_RELOAD` | `false` | Reloads plugin modules when Python files change. |
| `PLUGIN_AUTO_DISCOVERY` | `false` | Automatically discover plugins. |
| `ENABLE_PLUGIN_DEPENDENCY_RESOLUTION` | `false` | Resolve module dependencies during development. |

## Migration settings

| Variable | Default | Description |
| --- | --- | --- |
| `MIGRATION_MODE` | `auto` | `preview`, `auto`, or `full`. |
| `MIGRATION_BACKUP` | `false` | Create a database backup before non-preview migrations. |
| `MIGRATION_BACKUP_DIR` | `backups` | Backup directory. |
| `MIGRATION_AUTO_DROP` | `false` | Present for deployment scripts; migration runner uses `auto` safe filtering. |

## Redis

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_ENABLED` | `false` | Enable Redis service registration. |
| `REDIS_HOST` | `localhost` | Redis host. |
| `REDIS_PORT` | `6379` | Redis port. |
| `REDIS_DB` | `0` | Redis database number. |
| `REDIS_PASSWORD` | empty | Redis password. |

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
| `CHACC_DEPLOY_TIMEOUT` | `30` | HTTP timeout in seconds. |

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
