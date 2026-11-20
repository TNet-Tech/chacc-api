# Changelog


## 1.0.0-beta6

> Feature release: module dependencies, a web console for modules, automatic restarts, and production servers that start without network. Read **Before you upgrade** first.

**Update now:**
> PyPi Package:
```bash
pip install --upgrade chacc-api==1.0.0-b6
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-beta6
```

### Before you upgrade

- **Rebuild modules that depend on other modules.** Add `module_dependencies` to their `module_meta.json`, rebuild the `.chacc`, and deploy the modules they require first. See [Module dependencies](modules.md#module-dependencies).
- Deploying a module whose required modules are not installed is now refused with `409`.
- At startup, a module whose required modules are missing is skipped and listed in the log instead of crashing the server. While a module is skipped, `MIGRATION_MODE=full` runs as `auto` so its tables are kept.
- **Only admins can use the web console.** With the authentication module loaded, the core `/modules` and `/system` routes, the web console and `chacc deploy` need the `MANAGE_WEB_CONSOLE` privilege (set another with `CHACC_ADMIN_PRIVILEGE`) or `ALL`. ChaCC registers it with the authentication module itself. Other logged-in users now get `403`. Give deploy accounts a role with `MANAGE_WEB_CONSOLE`. See [Who can use it](console.md#who-can-use-it).
- **Protect servers without the authentication module** with `CHACC_CONSOLE_KEY`. The web console asks for it and `chacc deploy` sends `CHACC_DEPLOY_KEY`. Without it the server still works, but the console, the log and `chacc deploy` warn that it isn't protected. See [Without the authentication module](console.md#without-the-authentication-module).
- `POST /api/system/restart` is refused in development mode, where the server already reloads when files change.
- **Docker: add the `chacc_packages` volume** (`/app/.chacc_packages`) if you don't use the provided compose file. Module packages now live there.
- **Keep network available for the first start after upgrading.** Existing module packages were in the old container, so the first start installs them into the new volume. After that, starts need no network. Without network the affected modules are skipped until you run `chacc deps sync`.
- The images now use **Python 3.15** and pinned core package versions (`requirements.lock`).
- Requires `chacc-dependency-manager` 1.4.0 or newer.
- **SQLite: the first start rebuilds tables that are missing their foreign keys.** Rows are kept. `MIGRATION_BACKUP=true` now really backs up first.

## Added

- **Module dependencies** – Modules list required and optional modules in `module_meta.json` (`module_dependencies`). Modules load after the modules they depend on. `chacc install`, `chacc deploy` and the API check them, and missing optional modules only produce a warning. New modules created with `chacc create` include an empty list. See [Module dependencies](modules.md#module-dependencies).
- **Web console** – `/console` lists modules with their author, installs, enables, disables and uninstalls them, shows the dependency graph and restarts the server. It asks for a login when the authentication module protects the API. In development mode the dependency graph needs no login.
- **Dependency graph API** – `GET /api/modules/graph` returns the modules, their dependencies, which ones are blocked or missing, and the load order.
- **Automatic restarts** – `POST /api/system/restart` restarts the server gracefully, and `chacc run server` brings it back on its own. `chacc deploy --restart` deploys a module and makes it live in one step. See [Automatic Restarts](server-restarts.md).
- **Login prompt in `chacc deploy`** – When the server answers `401`, the CLI asks for a username and password, uploads with the token and revokes the session afterwards. `CHACC_DEPLOY_USERNAME`/`CHACC_DEPLOY_PASSWORD` cover CI.
- **Configurable API prefix** – `API_PREFIX` (default `/api`). Every core and module route is mounted under it. Clients discover it, and whether a login is needed, at `GET /.well-known/chacc`.
- **Large module uploads** – Uploads stream to disk in chunks. Packages up to 10 MB are accepted (`MAX_MODULE_UPLOAD_SIZE`), with a guard against zip bombs (`MAX_MODULE_UNCOMPRESSED_SIZE`).
- **Start without network** – In production, module packages are installed into `.chacc_packages/` (`MODULE_PACKAGES_DIR`, a volume in Docker) when a module is uploaded or enabled. Restarts and recreated containers reuse them. At startup the server only checks them; if some are missing it tries once (`CHACC_BOOT_INSTALL`) and otherwise skips just the modules that need them. See [Running without network](deployment.md#running-without-network).
- **`chacc deps check` and `chacc deps sync`** – Check the enabled modules' packages, or install what is missing.
- **Database helpers in `chacc_api.database`** – Route dependencies (`get_async_db`, `get_db`), blocks (`async with async_session()`, `with session()`) and decorators for functions and service classes (`@with_async_session`, `@with_session`). Each closes its session when the work ends. See [Database sessions](modules.md#database-sessions).
- **Rate limiting in `chacc_api.rate_limit`** – `rate_limit` for a route (with `key`, `cost`, `exempt_when`, `error_message` and `methods` options), `shared_rate_limit` for several routes sharing one limit, and `check_rate_limit` for things that aren't routes, such as login attempts. Routes can be limited where they are defined and don't need a `request` parameter. `RATE_LIMIT_ENABLED` and `RATE_LIMIT_STORAGE_URI` (memory or Redis) configure it. See [Rate limiting](modules.md#rate-limiting).
- **Optional Redis in Docker Compose** – `docker compose --profile redis up -d` adds a Redis container; ChaCC waits for it before starting. See [Redis (optional)](deployment.md#redis-optional).
- **Services tab in the web console** – Shows whether the database, Redis and rate limiting work, plus server details, checked every 30 seconds. The top bar shows when a service is down or degraded. Also available as `GET /api/system/services`. See [Service status](core-api.md#service-status).
- **Module details in the web console** – Click a module to see its state, routes, required and dependent modules, Python packages, archive, links and README (formatted as Markdown, with Mermaid diagrams drawn). A module that failed to load shows **Failed to load** with the reason, which is kept across restarts. Also available as `GET /api/modules/{name}`. See [Module details](core-api.md#module-details).
- **Console guide** – A new [Console](console.md) page walks through the modules, module details, dependency graph, services and restarts, with screenshots.

## Changed

- **New landing page** – Links to the web console and shows a live server status that follows restarts.
- `chacc deploy` waits up to 600 s for the server response by default (`CHACC_DEPLOY_TIMEOUT`) and exits with status `1` on failure.
- `chacc run server` now exits with the server's exit code when it crashes.
- Requests to `/.well-known/chacc` are no longer written to the access log.
- **Modules can't change core packages.** ChaCC's own installed versions are applied as constraints whenever module requirements are resolved, and the backbone is no longer resolved at runtime. Conflicts are refused at upload (`409`), unresolvable requirements return `422`, and an unreachable package index returns `503`. Nothing is installed or saved when this happens.
- The Docker entrypoint no longer resolves dependencies as root, and pip can't fall back to a per-user install that was lost when the container was recreated.
- Docker images use Python 3.15 and install core packages at the versions in `requirements.lock`.
- Disabling or uninstalling a module no longer contacts the package index.
- In development mode, settings that aren't allowed in production (such as an insecure `SECRET_KEY`) are logged as warnings instead of errors, since they don't stop the server there. Production still refuses to start.

## Deprecated

- `context.get_db` and `context.get_db_async` – Use `get_db` and `get_async_db` from `chacc_api.database`. They still work in this release and log a warning once.
- `context.limiter` – Use `chacc_api.rate_limit`. It still works in this release and logs a warning once.

## Fixed

- `docker stop` now shuts the server down gracefully.
- Docker health checks follow `API_PREFIX`.
- A `.chacc` file that is not a valid zip now returns `400` instead of `500`.
- Enabling a module now installs its own Python packages. They were skipped before.
- Docker images no longer contain module archives from the machine that built them.
- A failed dependency resolution is no longer remembered as a success (`chacc-dependency-manager` 1.4.0).
- Module discovery works with Python 3.15, which no longer uses `__package__` for imports.
- The development Docker image starts in development mode and builds again. The Docker files and `.env.example` used `DEVELOPMENT_MODE`, which ChaCC never read; the setting is `CHACC_DEV_MODE`. Rename it in your own `.env` if you copied it.
- `deploy.sh` (standalone Linux) works again: it started the service from the wrong folder with a command that doesn't exist, and the service could not write to most of its data folders. Running it again no longer replaces `.env` and its secrets.
- Module discovery at startup no longer leaves its database session to be closed by the garbage collector.
- `import chacc_api.database` and `import chacc_api.core` failed with `ImportError`.
- The rate-limiting example in the docs crashed at import: SlowAPI routes need a `request` parameter. `rate_limit` doesn't.
- A rate-limited route defined again (module hot reload) counted every request twice.
- Modules made with `chacc create` now use `chacc_api.database` for sessions, so they don't log deprecation warnings.
- `docker-compose.dev.yml` runs `chacc run server --dev` like the development image, works on its own, and mounts `chacc_api/`. It ran bare `uvicorn` and mounted files the server doesn't use. The development image runs as your user, so it can read mounted modules whose folders only you can open.
- When a module's code couldn't be imported (for example a missing package), the error was hidden behind a misleading one such as "setup function not found". The real error is now reported.
- If Redis was down when the server started, modules never got it, even after Redis came back. The server now registers Redis whenever it is enabled and connects as soon as Redis is reachable.
- An unreachable Redis no longer slows the server down: each connection attempt took about 4.5 seconds because of retries. It now fails at once and is tried again at most every 10 seconds.
- After an upgrade, the console and landing page could keep running the browser's old cached script and styles, so new features (such as the Services tab) stayed empty until a hard refresh. Their links now include a fingerprint of the file's contents, so a changed file is always fetched again.
- In production, the console page was cached until a restart even when its files changed, so it could show headings that didn't match its script. It is now rebuilt when its files change.
- In development mode with `ENABLE_PLUGIN_HOT_RELOAD=True`, editing a module in `plugins/` restarts the server again. An earlier beta 6 change had limited the reload to `src/`.
- In development mode, the server didn't start when a data folder such as `MODULES_INSTALLED_DIR` was outside the project folder ("Non-relative patterns are unsupported").
- **SQLite tables were created without their foreign keys**, so relationships and `ondelete` did nothing. Tables now get them, and existing tables get them at the next start. Enforcing them is opt-in with `SQLITE_FOREIGN_KEYS=true`. See [Foreign keys on SQLite](database-migrations.md#foreign-keys-on-sqlite).
- **`MIGRATION_BACKUP=true` never created a backup.** It now backs up before a migration that changes the database, in `auto` and `full` mode. SQLite backups are taken safely while the server runs and are restored if the migration fails.
- **`MIGRATION_MODE=full` planned to drop every module's tables at each start** and recorded operations it never ran as applied. Only a bug prevented the drops. Tables are now never dropped automatically, removals wait until every module has loaded, and the migration log only lists what was applied.
- When nginx or another proxy refused a module as too large, `chacc deploy` printed the proxy's HTML error page. It now says the proxy refused it and which setting to raise. See [Behind a reverse proxy](deployment.md#behind-a-reverse-proxy).

## 1.0.0-beta5.3

> Patch release with bug fixes and improvements. For initial module scaffold failures, patch to this version.

**Update now:**
> PyPi Package:
```bash
pip install --upgrade chacc-api==1.0.0-b5.post3
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-beta5.3
```

## Added

- **All branches on install** – `chacc install` now fetches all branches by default. Use `--single-branch` to opt out.

- **Contributors section** – README and overview docs now include a contributors table.

- **`chacc doctor` command** – New diagnostic command to check your ChaCC installation health.

## Fixed

- **CLA workflow** – Fixed file extension, branch reference, and allowlist format so CLA signing works correctly.

- **Label sync** – Quoted color values in labels.yml so YAML no longer misparses hex colors as numbers.

- **Install command** – Fixed development mode install to fetch all branch info by default.

- **`chacc create` command** – Fixed a bug that prevented module scaffolding from working.

## 1.0.0-beta5.2

> Note: This version fixes the production startup issues specifically in docker image. If you plan to deploy with docker, then this is a must have version.


**Update now:**
> PyPi Package:
```bash
pip install --upgrade chacc-api==1.0.0-b5.post2
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-beta5.2
```

## Added

- **Quieter logs** – Docker health checks no longer spam your logs. The server still checks its health every 30 seconds, but those checks stay silent unless something's actually wrong.

- **Version endpoint** – `GET /api/version` now tells you which version of ChaCC API you're running, along with the Python version. The welcome page and status badge read from this automatically, so what you see is always accurate for your running build.

- **Smarter Docker startup** – The Docker entrypoint now creates all the data directories it needs (modules, cache, backups, plugins) and sets the right permissions at startup. Any new volume you mount under `/app` just works – no script editing, no rebuilding.

---

## Fixed

- **Temp folders no longer sneak into your `.chacc` files** – When you built a module, a leftover temp folder could get packaged into the archive. That caused import errors and duplicate module structures when the server loaded it. Now the build skips temp folders, and the server cleans them up if they somehow slip through – so existing deployments get fixed too.

- **Removed pointless health check tracking** – The server used to track dependency resolution progress and show it on the health endpoint. But by the time dependencies are being resolved, the server isn't accepting requests yet – so nobody could see it. That whole mechanism (and the related frontend spinner) is gone. Less code, less noise.

- **PostgreSQL works out of the box now** – ChaCC now uses `psycopg[binary]`, which bundles the PostgreSQL client library right inside the Python package. No more installing `libpq` system-wide or compiling anything. The server starts cleanly on minimal images like `python:3.12-slim` and in fresh virtual environments. Just install and go.

- **Docker permission errors fixed** – Several small permission issues that could stop the server from starting in Docker are now resolved:
  - The dependency cache directory is created and used correctly.
  - The `chacc` user's home directory is set up properly, so `pip-tools` no longer fails.
  - The Docker build includes the entrypoint script correctly.

- **Newly installed modules now get their dependencies** – This was a big one. Previously, if you deployed a module that needed extra packages, the server would try to resolve them before the module was even registered in the database. Result: the module loaded without its dependencies and crashed with an `ImportError`. Now the server registers the module first, then resolves dependencies – so everything installs correctly.

- **Dependencies now install properly in Docker** – In Docker, dependency installation used to run as the `chacc` user, which doesn't have permission to write to `site-packages`. So dependencies were never actually installed, and modules failed to load. Now dependency resolution runs as root before the server starts, then drops to the `chacc` user. Modules work as expected.

---

## 1.0.0-beta5.1


**Update now:**
> PyPi Package:
```bash
pip install --upgrade chacc-api==1.0.0-b5.post1
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-beta5.1
```

### Fixed

- **psycopg3 migration** – ChaCC now uses the modern `psycopg` (psycopg 3) driver for both synchronous and asynchronous PostgreSQL connections. The CLI and server no longer require the legacy `psycopg2` package, so database connections work cleanly on Python 3.12 and newer.
- **CLI no longer loads the database** – The `chacc` command-line tool is now fully independent from the server package. Running `chacc --help`, `chacc create`, `chacc build`, or `chacc install` no longer initializes a database engine or requires database drivers, making the CLI faster and safer to use anywhere.
- **Lazy package loading** – Importing `chacc_api` is now lightweight. Database-backed components like `ChaCCBaseModel`, `ModuleRecord`, and the database engine are only loaded when you actually use them, so lightweight tools and scripts can import the package without side effects.
- **Colored CLI output** – Install progress, warnings, and results now use text colors (green for success, red for failure, yellow for warnings) to make terminal output easier to read. Colors automatically turn off in CI logs and pipes.

---

## 1.0.0-b5


**Update now:**
> PyPi Package:
```bash
pip install --upgrade chacc-api
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-b5
```

### Added

- **`chacc install` command** – Install any ChaCC module from a Git repository or local folder in one step. You can use a full URL, an SSH address, or the short form like `TNet-Tech/chacc_outbound`. Use `--dev` to copy the module into the plugins directory for active development, or leave it off to build a production `.chacc` archive automatically. Supports `--ref` for branches, tags, and commits, `--force` to overwrite existing modules, and private repositories via `GITHUB_TOKEN`, `GITLAB_TOKEN`, `BITBUCKET_TOKEN`, or `CHACC_GIT_TOKEN`. Includes a friendly step-by-step progress display with colored status markers so you always know what is happening. See the [CLI install guide](cli.md#install-a-module) for the full reference.


- **Async database support for modules** – Modules can now connect to the database without blocking the server. When you create a new module with `chacc create`, the generated code includes everything needed to run database queries asynchronously.
- **Chacc Outbound module** – A new official module for sending emails, SMS, and other messages. It includes automatic retries, delivery status tracking, and a pluggable adapter system (SMTP and console adapters included out of the box). See the [Chacc Outbound docs](official-modules/outbound.md) for setup, REST API, and how to write custom adapters.

### Fixed

- **Database connections leaking in generated code** – The scaffolded `get_db` dependency now properly closes the database session after each request, preventing connection leaks over time.
- **Docker startup issues** – Fixed a problem where the database failed to migrate during startup in production mode.
- **Docker permission errors** – Fixed a permission issue that prevented the dependency resolver from writing its cache.
- **PostgreSQL enum migration crashes** – Fixed a crash when changing a column from one enum type to another. ChaCC now handles the conversion smoothly through an intermediate step, so enum migrations work without manual SQL.
- **Module loading crashes** – Fixed a crash that occurred when some plugins loaded their models in certain orders. The startup process is now more forgiving and handles edge cases gracefully.
- **Migration crashes** – Improved how ChaCC reads migration plans from Alembic, eliminating rare crashes during database updates.
- **Code cleanup** – Removed unreachable error handling code and eliminated an unnecessary global directory change during archive building, making the install flow easier to follow and safer in multi-threaded environments.

### Changed

- **Module name validation enforced in build path** – `chacc build` and the internal build step of `chacc install` now both normalize module names the same way. This ensures that module names behave consistently whether you are building a package or installing one.

---

## 1.0.0-b4.5


**Update now:**
> PyPi Package:
```bash
pip install chacc-api==1.0.0-b4.post3
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-b4.5
```

### Changed

- **Module naming convention** – Module directories now use underscores instead of hyphens (for example, `chacc_file_manager` instead of `chacc-file-manager`) to match Python naming standards. This makes the import system work consistently across the module loading pipeline. If you have existing modules, rename your module directories and update the `name` field in `module_meta.json`.
- **Code formatting tool** – Switched from Black to Ruff formatter. All code is now formatted using `ruff format` with the same 100-character line length. You can run `ruff format .` to auto-format and `ruff format --check .` to verify formatting.
- **Documentation workflow** – Documentation Docker images are now built and pushed automatically when a release is published. Manual documentation builds can be triggered by including "build docs" in a commit message on the develop or main branch, or via the workflow_dispatch workflow in GitHub Actions.
- **Changelog location** – The changelog has been moved to `chacc-docs/docs/changelog.md`. The root `CHANGELOG.md` file has been removed. See the [changelog on chacc.dev](https://chacc.dev/changelog) for the complete history.
- **ChaCC Theme Applied in Swagger UI and ReDoc** - Added custom ChaCC theme styling to Swagger UI and ReDoc interfaces for consistent branding.

### Added

- **Manual Docker workflows** – Added separate workflows for manual Docker builds:
  - `.github/workflows/docker-manual.yml` – Build and push main Docker image on demand
  - `.github/workflows/docker-docs-manual.yml` – Build and push documentation Docker image on demand


### Fixed

- **Module loading duplicate class registration** – Fixed "Multiple classes found for path" SQLAlchemy errors when loading modules by refactoring the discovery and setup phases to use a consistent import mechanism. Both phases now use the same module objects from `sys.modules`, eliminating duplicate SQLAlchemy declarative registry entries.

- **AutoIncrement Indexed ID** – Fixed auto-increment behavior for indexed primary keys from `ChaCCBaseModel`.

> **AutoIncrement Indexed ID** is a breaking change. Ensure to backup your database before upgrading.


---

## 1.0.0-b4.2

**Update now:**
> PyPi Package:
```bash
pip install chacc-api==1.0.0-b4.post2
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-b4.2
```

**Beta4.2 fixes a critical startup crash, resolves the audit-schema chicken-and-egg problem, and cleans up model discovery. We have brought you better landing page. If you've had issues with module loading or SQLite table detection, this release is for you.**

---

### Added

- **Smarter model discovery** – Modules now load their dependencies in the correct order automatically, even when imports are nested.
- **Better migration safety** – New dependency resolver and operation executor handle PostgreSQL enum conflicts and ensure migrations run correctly across SQLite and PostgreSQL.
- **Comprehensive test coverage** – Tests now cover migration ordering, safe operation filtering, schema reflection, and model discovery.
- **HTML welcome page** – Adds a dark-mode HTML welcome page with links to Swagger UI, ReDoc, and chacc.dev documentation, replacing the raw JSON root endpoint.


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

## 1.0.0-b4.1

**Update now:**
> PyPi Package:
```bash
pip install chacc-api==1.0.0-b4.post1
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-b4.1
```

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
- SQLite database path handling so `SQLITE_DATABASE_PATH` and `SQLITE_DATABASE_NAME` configuration takes effect.

### Removed

- Removed redundant `LogLevels.INFO` logger setup across server, database, migration, module loader, Redis, health, and environment validation modules.
- Removed stale Docker `8080` exposed port and health check references.
- Removed local-build instructions from the production Docker Compose file.

### Changed

- README file has been updated to focus on ChaCC brief intro and link the entire guidance to [chacc.dev](https://chacc.dev)

## 1.0.0-b4

**Update now:**
> PyPi Package:
```bash
pip install chacc-api==1.0.0-b4
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-b4
```

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
