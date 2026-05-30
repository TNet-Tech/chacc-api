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

## [1.0.0-b3] - 2026-05-26

### Added
- Automatic creation of `.env` file from `.env.sample` if `.env` does not exist on application startup, providing a ready-to-use configuration reference.
- Included `.env.sample` in the package distribution to ensure it is available when the package is installed.

### Fixed
- Improved migration engine to be able to distinguish default database vs postgres database accordingly.