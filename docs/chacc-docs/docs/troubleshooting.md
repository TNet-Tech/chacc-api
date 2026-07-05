# Troubleshooting

## Server will not start

Check environment validation first.

```bash
chacc run server --debug
```

Common causes:

| Symptom | Fix |
| --- | --- |
| `SECRET_KEY is required in production mode` | Set a strong `SECRET_KEY`. |
| `SECRET_KEY must be at least 32 characters` | Use a longer random secret. |
| `SECRET_KEY matches insecure pattern` | Replace default or test-like values. |
| `DATABASE_HOST is required when using PostgreSQL` | Set `DATABASE_HOST`. |
| `DATABASE_USER is required when using PostgreSQL` | Set `DATABASE_USER`. |
| `DATABASE_PASSWORD is required when using PostgreSQL` | Set `DATABASE_PASSWORD`. |
| `DATABASE_NAME is required when using PostgreSQL` | Set `DATABASE_NAME`. |
| `ENABLE_PLUGIN_HOT_RELOAD must be disabled in production` | Set it to `false`. |
| `PLUGIN_AUTO_DISCOVERY must be disabled in production` | Set it to `false`. |

## Module fails to load

Check the logs for the module name and entry point.

Common causes:

| Symptom | Fix |
| --- | --- |
| Invalid `entry_point` | Use `package.module:function` format. |
| Entry point file not found | Confirm the file path in `entry_point` exists. |
| Setup function not found | Export `setup_plugin` or the function named in metadata. |
| Setup function returns wrong type | Return a FastAPI `APIRouter`. |
| Relative import issue | Import from the module package, not from sibling paths. |
| Dependency resolution failed | Add required packages to `requirements.txt`. |
| Module discover-loading mismatch with `PLUGIN_AUTO_DISCOVERY=False` | Ensure module metadata, entry points, and base paths are correctly stored in the `modules` table when skipping filesystem discovery. |

Restart the backbone after installing, enabling, disabling, or uninstalling a
module.

## Migration fails

| Symptom | Fix |
| --- | --- |
| `Multiple classes found for some modules` | Normalize imports to the bare module prefix and remove `@register_model` decorators. This crash was caused by stale `sys.modules` entries and dual `_model_registry` + `metadata_obj` registration. |
| Destructive operation skipped | This is expected in `MIGRATION_MODE=auto`; use `full` only when intentional. |
| Backup failed | Confirm `MIGRATION_BACKUP_DIR` is writable. |
| SQLite table already exists | Usually handled by idempotency; inspect logs for non-duplicate errors. |
| Spurious SQLite `add_table` migrations for existing tables | Verify `SQLITE_DATABASE_PATH` and that `table_exists` is returning correct results. This was fixed in 1.0.0-b4.2 by no longer passing `schema=public` to SQLite's `get_table_names()`. |
| PostgreSQL enum sync skipped | Install `alembic-postgresql-enum`. |
| PostgreSQL enum migration fails | Confirm `alembic-postgresql-enum` is installed and enum metadata changes are expected. |
| Migration dependency error | The runner validates that referenced tables exist or have pending `add_table` migrations. Missing foreign-key targets now raise explicit errors. |
| Migration timeout | Review long-running operations and database locks. |

Preview changes without applying them:

```bash
MIGRATION_MODE=preview chacc run server
```

## Database issues

| Symptom | Fix |
| --- | --- |
| SQLite database missing | Start the server once to create `chaccapi.db`, or check `SQLITE_DATABASE_NAME` and `SQLITE_DATABASE_PATH`. |
| SQLite database created in wrong directory | Confirm `SQLITE_DATABASE_PATH` points to the intended directory. |
| Cannot write database file | Confirm `SQLITE_DATABASE_PATH` exists and is writable. |
| `SQLITE_DATABASE_NAME` ignored | Ensure it is a file name without path separators; use `SQLITE_DATABASE_PATH` for the directory. |
| PostgreSQL connection refused | Confirm host, port, user, password, and database. |
| Readiness check reports database error | Check database credentials and network access. |
| Migration tracker table missing | The runner creates it on startup. |

## Redis issues

If Redis is enabled but unavailable, the backbone logs a warning and continues
without Redis.

Check:

```bash
REDIS_ENABLED=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

## Deployment issues

| Symptom | Fix |
| --- | --- |
| `chacc deploy` cannot connect | Confirm `CHACC_DEPLOY_URL` points to a running API. |
| Deployment times out | Increase `CHACC_DEPLOY_TIMEOUT`. |
| Deployment returns 401 | Set `CHACC_DEPLOY_API_KEY` to a valid bearer token. |
| Module installed but not active | Restart the remote ChaCC API server. |
| Docker health check fails | Confirm container and host port mapping use `8085` and health endpoint is `/health`. |

## Logging issues

| Symptom | Fix |
| --- | --- |
| Missing verbose logs | Use `CHACC_VERBOSE=true` or `chacc run server -v`. |
| Missing debug logs | Use `CHACC_DEBUG=true` or `chacc run server --debug`. |

## Clean reset

For local development only, stop the server and remove generated state:

```bash
rm -rf .modules_loaded .modules_installed .chacc_cache backups chaccapi.db
```

If you changed the SQLite database location or file name using `SQLITE_DATABASE_PATH` or `SQLITE_DATABASE_NAME`, remove that file as well.

Do not run this on production data unless you intend to delete the database and
installed modules.
