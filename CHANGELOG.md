## [1.0.0-b3.2] - 2026-05-26

### Added
- Automatic creation of `.env` file from `.env.sample` if `.env` does not exist on application startup, providing a ready-to-use configuration reference.
- Included `.env.sample` in the package distribution to ensure it is available when the package is installed.


### Fixed
- Improved migration engine to be able to distinguish default database vs postgres database accordingly