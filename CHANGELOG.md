# Changelog

**Update now:**
```bash
pip install --upgrade chacc-api
```

## 1.0.0-b4.2

**Beta4.2 fixes a critical startup crash, resolves the audit-schema chicken-and-egg problem, and cleans up model discovery. If you've had issues with module loading or SQLite table detection, this release is for you.**

---

### Added

- **Smarter model discovery** – Modules now load their dependencies in the correct order automatically, even when imports are nested.
- **Better migration safety** – New dependency resolver and operation executor handle PostgreSQL enum conflicts and ensure migrations run correctly across SQLite and PostgreSQL.
- **Comprehensive test coverage** – Tests now cover migration ordering, safe operation filtering, schema reflection, and model discovery.

### Fixed

- **Startup crash** – Fixed "Multiple classes found for some modules" crash that occurred when plugin discovery was disabled in development mode.
- **Double model registration** – Removed the old `_model_registry` and now rely exclusively on SQLAlchemy's declarative metadata. No more duplicate table errors.
- **SQLite table detection** – Fixed a bug where `table_exists()` returned incorrect results for existing tables.
- **Audit schema chicken-and-egg** – Split schema initialization into two passes (before and after entry points) so audit fields are applied correctly even when the `enable_audit_fields` service is registered after startup.
- **Module load failure handling** – Failed modules are now properly disabled, preventing repeated crash loops on restart.
- **Logging crashes** – Fixed crashes when logging routes that had `None` paths or methods.

### Changed

- **Module loading sequence** – Both dev and prod modes now follow the same sequence: discover models → initialize database → run migrations → load entry points → apply deferred schema changes → optional follow-up migration.
- **Database initialization** – Now uses `ChaCCBaseModel` subclass enumeration instead of the removed `_model_registry`.

### Removed

- **Redundant startup schema pass** – Removed a duplicate migration run that caused unnecessary migrations in some environments.
- **`_model_registry`** – The old model registry has been removed in favor of SQLAlchemy's declarative metadata.

### Notes

- **Versioning**: The package metadata uses `1.0.0-b4.post2` for PyPI; the user-facing version is `1.0.0-b4.2`. Both refer to the same release.
- **Port default**: All references now consistently use port `8085` (previously some docs mentioned `8080`).
- **`.env` behavior**: The `.env.sample` file is copied from the package to your working directory if missing. This is intentional and unchanged from previous versions.

---


## [1.0.0-b4.2] - 2026-07-02

**Beta4.2 fixes a critical startup crash, resolves the audit-schema chicken-and-egg problem, and cleans up model discovery. If you've had issues with module loading or SQLite table detection, this release is for you.**

---

### Added

- **Smarter model discovery** – Modules now load their dependencies in the correct order automatically, even when imports are nested.
- **Better migration safety** – New dependency resolver and operation executor handle PostgreSQL enum conflicts and ensure migrations run correctly across SQLite and PostgreSQL.
- **Comprehensive test coverage** – Tests now cover migration ordering, safe operation filtering, schema reflection, and model discovery.

### Fixed

- **Startup crash** – Fixed "Multiple classes found for some modules" crash that occurred when plugin discovery was disabled in development mode.
- **Double model registration** – Removed the old `_model_registry` and now rely exclusively on SQLAlchemy's declarative metadata. No more duplicate table errors.
- **SQLite table detection** – Fixed a bug where `table_exists()` returned incorrect results for existing tables.
- **Audit schema chicken-and-egg** – Split schema initialization into two passes (before and after entry points) so audit fields are applied correctly even when the `enable_audit_fields` service is registered after startup.
- **Module load failure handling** – Failed modules are now properly disabled, preventing repeated crash loops on restart.
- **Logging crashes** – Fixed crashes when logging routes that had `None` paths or methods.

### Changed

- **Module loading sequence** – Both dev and prod modes now follow the same sequence: discover models → initialize database → run migrations → load entry points → apply deferred schema changes → optional follow-up migration.
- **Database initialization** – Now uses `ChaCCBaseModel` subclass enumeration instead of the removed `_model_registry`.
- **Root endpoint** – `/` now serves a dark-mode HTML welcome page with links to Swagger UI, ReDoc, and chacc.dev documentation, instead of returning raw JSON. The page embeds the ChaCC logo and uses the project's teal/navy color theme.
- **Docs theming** – Swagger UI and ReDoc are now themed to match the ChaCC teal/navy dark mode, using the same color palette as the welcome page. Custom CSS is injected directly into standalone docs pages built from CDN resources. Buttons use teal outlines with white text and teal backgrounds on hover. Cancel/danger buttons are dark with a red hover state. Titles, loaders, and all text use theme colors.

### Removed

- **Redundant startup schema pass** – Removed a duplicate migration run that caused unnecessary migrations in some environments.
- **`_model_registry`** – The old model registry has been removed in favor of SQLAlchemy's declarative metadata.

### Notes

- **Versioning**: The package metadata uses `1.0.0-b4.post2` for PyPI; the user-facing version is `1.0.0-b4.2`. Both refer to the same release.
- **Port default**: All references now consistently use port `8085` (previously some docs mentioned `8080`).
- **`.env` behavior**: The `.env.sample` file is copied from the package to your working directory if missing. This is intentional and unchanged from previous versions.

---

**Update now:**
```bash
pip install --upgrade chacc-api
```

## [1.0.0-b4.1] - 2026-06-19

### Added
- PostgreSQL enum migration support through `alembic-postgresql-enum`, including handling for `create_enum`, `sync_enum_values`, and `drop_enum` operations.
- Migration runner support for Alembic PostgreSQL enum operation objects generated by `alembic-postgresql-enum`.
- Automatic enum type creation before adding enum-backed columns or tables in PostgreSQL migrations to prevent `UndefinedObject` failures.
- `uuid7`-based default UUID generation for `ChaCCBaseModel`, using Python 3.12+ `uuid.uuid7` with `uuid-utils` fallback on older Python versions.
- `uuid-utils` runtime dependency for environments without native `uuid7` support.
- `SQLITE_DATABASE_NAME` and `SQLITE_DATABASE_PATH` environment variables for custom SQLite database names and storage locations.
- `CHACC_VERBOSE` and `CHACC_DEBUG` environment controls for runtime log level selection.
- CLI `chacc run server -v/--verbose` support that now propagates verbose logging into the server subprocess.
- Docker health checks and exposed ports updated to the current default server port.
- Production Docker Compose now uses the published Docker Hub image directly instead of local image build comments.

### Fixed
- PostgreSQL migration failures when Alembic detects enum changes by importing and enabling `alembic-postgresql-enum` hooks.
- PostgreSQL `UndefinedObject` crashes when adding enum-backed columns or tables by creating enum types before table/column operations.
- Migration operation ordering to apply enum creation before tables, columns, constraints, indexes, and enum synchronization.
- Migration descriptions for enum create, sync, and drop operations.
- CLI verbose flag propagation so `chacc run server -v` affects the child server process.
- Docker and Docker Compose default port mismatch by replacing stale `8080` references with `8085`.
- Alembic log noise by forcing the `alembic` logger to `WARNING`.
- Default logging behavior so normal server runs are quieter while `CHACC_VERBOSE` and `CHACC_DEBUG` still enable detailed logs.
- Repeated logger imports by centralizing default log level detection in `get_default_log_level()`.
- SQLite database path handling so `SQLITE_DB_PATH` uses the configured `SQLITE_DATABASE_PATH` and `SQLITE_DATABASE_NAME`.

### Removed
- Removed redundant `LogLevels.INFO` logger setup across server, database, migration, module loader, Redis, health, and environment validation modules.
- Removed stale Docker `8080` exposed port and health check references.
- Removed local-build instructions from the production Docker Compose file.

### Changed
- README file has been updated to focus on ChaCC brief intro and link the entire guidance to [chacc.dev](https://chacc.dev)

## [1.0.0-b4] - 2026-05-30

### Added
- **Breaking**: GUID TypeDecorator for cross-database UUID support (PostgreSQL UUID type / SQLite TEXT storage)
- SQLite batch operation support for constraints, indexes, and columns via `batch_alter_table()`
- Automatic `.env` file creation from `.env.sample` on application startup if `.env` does not exist
- `.env.sample` included in package distribution for ready-to-use configuration reference
- Migration version counter suffix to prevent duplicate migration versions
- New database engine detection to distinguish PostgreSQL vs other databases

### Fixed
- **Breaking**: Migration tracker table `rollback_available` column conversion from BOOLEAN to INTEGER for PostgreSQL, and compatibility for SQLITE
- Migration runner now uses `run_in_executor()` for synchronous DB operations to prevent blocking async event loop
- Made tracker/backup lazy properties to defer DB initialization
- Catch ProgrammingError/OperationalError for already-existing resources to make migrations idempotent
- GUID TypeDecorator now returns UUID instances directly without unnecessary conversion
- Tracker table now filtered from migration detection to prevent accidental drops
- Resolved requirements.txt path issue for installed package layout

### Removed
- Removed redundant database type conversion in GUID TypeDecorator

> **Caution:** Users migrating to 1.0.0-b4 will need to drop their existing databases and start afresh. The `rollback_available` column type changed from BOOLEAN to INTEGER, and GUID column changes require a clean schema migration that cannot be automatically applied to existing data.
