## [Unreleased]

### Added

**Who Uses ChaCC?**
- **Jonas** — uses ChaCC API for development of modules such as the [Official Authentication Module](https://github.com/Jonas1015/chacc-authentication).


---

## [1.0.0-b3.1] - 2026-05-21

### Added

- `--dev` flag for hot reloading (`chacc run server --dev`).
- Module discovery now supports nested packages.
- Module Scaffolding now provides a `get_db()` function via
  `context_factory`, enabling direct `Depends` usage by modules.

**CORS Configuration**

Configurable CORS settings via environment variables:

- `CORS_ALLOWED_ORIGINS` — comma-separated allowed origins
- `CORS_ALLOW_CREDENTIALS` — enable/disable credentials
- `CORS_ALLOW_METHODS` — allowed HTTP methods
- `CORS_ALLOW_HEADERS` — allowed headers

**CLI Server Commands**

New CLI flags for controlling server mode:

- `chacc run server --dev` — Development mode with hot reload
- `chacc run server` — Production mode without auto-reload
- Removed `DEVELOPMENT_MODE` environment variable in favour of `--dev`, which internally sets `CHACC_DEV_MODE`

### Changed

- `DEVELOPMENT_MODE` — replaced as a public environment variable by the
  `--dev` CLI flag; the legacy `CHACC_DEV_MODE` env var (set by the CLI at
  runtime, not intended for manual use) is used internally by `src/constants.py`.
- `run_automatic_migration` — removed; replaced by `run_migration` from the new
  `src/migration/runner.py` system, which ships with schema tracking, backup
  support, and preview mode.
- `DevBackboneContext` — removed from the CLI scaffold; `context_factory` now
  raises `RuntimeError` when no backbone context is present, forcing modules to
  run inside the backbone.
- Module loading is now two-phase: models are discovered and imported first,
  then database migrations are applied, and finally the setup functions run.
  This prevents race conditions where setup code executed before migrations
  completed.
- Startup no longer blocks on Redis if unavailable.

### Deprecated

- `DEVELOPMENT_MODE` environment variable — renamed to `CHACC_DEV_MODE`.
  Existing direct reads of `DEVELOPMENT_MODE` (other than blanket `DEVELOPMENT_MODE`
  in `src/constants.py`) will be removed in a future release. Internal module
  definitions in `src/` have already been migrated to the new variable name.
- `run_automatic_migration` — removed in v1.0.0-b3.1; replaced by `run_migration`.

### Fixed

- Critical timing race fixed: plugin setup functions previously ran before
  database migrations. Modules now follow a two-phase ordered load:
  discover models → run migrations → execute setup functions.
- Redis no longer starts enabled by default (`REDIS_ENABLED=False`), removing a
  ~5-second startup wait on systems without Redis.
- Redis socket connect timeout and socket timeout both reduced from 5 s to 2 s,
  giving faster failure detection. Redis connection-failure log level lowered
  from `error` to `debug` for cleaner startup output.
- Fix CLI start-server command for production mode (now reads host/port from
  `CHACC_HOST` / `CHACC_PORT` environment variables).
- Fix `start_server.py` path resolution under an installed layout.
- Remove `DevBackboneContext` from CLI scaffold (simplified context factory).
- Resolve relative import errors by loading sibling Python files before
  `__init__.py` during model discovery.
- Environment validator now uses pre-loaded constants rather than repeated
  `decouple.config()` calls, eliminating startup disk I/O.
- Remove backbone test execution from the server startup path; tests are no
  longer run at import time.
- Apply BASE_DIR-based path resolution for requirements.txt lookups across
  multiple callers (`chacc_dependency_manager.py`, `module_loader/archive.py`,
  `modules.py`, `plugin_loader.py`).
- Remove unused imports from `src/database.py` (leftover `alembic` imports removed).
- Formatting and linting fixes in `chacc_api/__init__.py`, `start_server.py`, and `chacc_cli/__main__.py`.
