# Overview

## The problem ChaCC solves

Tired of setting up the same API boilerplate? ChaCC is a running server out of the box. Build an API module once, share it like a meme (but actually useful), and deploy it anywhere a ChaCC instance runs. Stop rebuilding. Start shipping.



## What ChaCC is

ChaCC API is a modular FastAPI application platform where modules own their domain logic and mount their own FastAPI routers into the backbone.

The backbone owns the HTTP server, configuration validation, database engine, and database migrations, module registry, dependency resolution, rate limiting, and CLI tooling.

## Current pre-release

| Item | Value |
| --- | --- |
| Package | `chacc-api` |
| Version | `1.0.0-b5.3` |
| Runtime | Python 3.10, 3.11, or 3.12 |
| Web framework | FastAPI |
| Database | SQLite by default, PostgreSQL supported |
| License | Apache-2.0 |

## Core concepts

### Backbone

The backbone is the FastAPI application which validates the environment, initializes the database, runs
migrations, and loads modules.

### Module

A module is a fastapi application plus a `module_meta.json` file. A module can include
models, routes, services, tests, and requirements. It is loaded by the backbone
through an entry point function which returns FastAPI `APIRouter`.

### `.chacc` package

A `.chacc` package is an archive containing the module source, metadata, and
optional `requirements.txt`. The CLI builds this archive with `chacc build` command.

### BackboneContext

`BackboneContext` is passed into each module's `setup_plugin(context)` function.
It exposes shared services:

| Context member | Purpose |
| --- | --- |
| `context.app` | Main FastAPI application. |
| `context.limiter` | SlowAPI limiter for route-level throttling. |
| `context.logger` | Centralized logger. |
| `context.get_db` | Database session dependency. It is a synchronous session and should be treated as such. |
| `context.get_db_async` | Async database session dependency. Use this for non-blocking database access; works with `AsyncSession`. |
| `context.register_service()` | Register a named service for other modules. |
| `context.get_service()` | Retrieve a named service. |
| `context.get_module_config()` | Read module-specific environment configuration. |

## Runtime startup flow

```mermaid
flowchart TD
    A[FastAPI lifespan starts] --> B[Validate environment]
    B --> C[Create BackboneContext]
    C --> D[Initialize Redis when enabled]
    D --> E[Discover module models via AST topological import]
    E --> F[Initialize database models]
    F --> G[Run database migrations]
    G --> H{Development mode?}
    H -->|Yes| I[Load plugins from plugins/ ]
    H -->|No| J[Load modules from .modules_installed/]
    I --> K[Mount module routers]
    J --> K
    K --> L[API ready]
```

## Architecture

```mermaid
flowchart LR
    subgraph Backbone[ChaCC backbone]
        API[FastAPI app]
        Context[BackboneContext]
        DB[(SQLAlchemy engine)]
        Migrations[Migration runner]
        Loader[Module loader]
        Redis[(Redis optional)]
    end
    subgraph Modules[Installed modules]
        Auth[Authentication module]
        Feature[Feature module]
    end
    API --> Context
    Context --> DB
    Context --> Redis
    Context --> Migrations
    Context --> Loader
    Loader --> Auth
    Loader --> Feature
```

## Module lifecycle

1. **Discover**: the loader scans installed `.chacc` archives or development
   plugin directories.
2. **Resolve dependencies**: module requirements are combined with backbone
   requirements and resolved through the dependency manager.
3. **Extract**: archives are unpacked into `.modules_loaded/`.
4. **Synchronize**: `ModuleRecord` rows are created, updated, or removed.
5. **Discover models**: Python files are imported so `ChaCCBaseModel`
   subclasses are added to SQLAlchemy declarative metadata.
6. **Migrate**: the migration runner compares metadata with the database.
7. **Mount**: each enabled module returns an `APIRouter`, which the backbone
   includes at the configured prefix.

## Core API surface

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/` | `GET` | Welcome message for the backbone. |
| `/api/health` | `GET` | Basic liveness check. |
| `/api/health/ready` | `GET` | Readiness check including database connectivity. |
| `/api/health/live` | `GET` | Lightweight process liveness check. |
| `/api/modules` | `POST` | Upload and install a `.chacc` module package. |
| `/api/modules` | `GET` | List installed module records. |
| `/api/modules/{module_name}/enable` | `POST` | Mark a module enabled. Requires restart. |
| `/api/modules/{module_name}/disable` | `POST` | Mark a module disabled. Requires restart. |
| `/api/modules/{module_name}/uninstall` | `DELETE` | Remove module archive, extracted code, and DB record. Requires restart. |

---

## Contributors

ChaCC API exists because people gave their time to make it better.

To everyone who has opened an issue, fixed a bug, improved a sentence of documentation, asked a hard question, or simply tried the beta and told us what broke, thank you so much. You are the reason this project moves forward.

If you'd like to join us, you're welcome here. There is no contribution too small. A typo fix, a clearer error message, a test, a module idea, or a kind word in a discussion all count. Check out [CONTRIBUTING.md](https://github.com/TNet-Tech/chacc-api/blob/develop/CONTRIBUTING.md) to get started, and know that your name will appear below when you do.


<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/jonas1015"><img src="https://avatars.githubusercontent.com/u/54990284?v=4&size=100" width="100px" height="100px" alt="Jonas G Mwambimbi"/><br /><sub><b>Jonas G Mwambimbi</b></sub></a><br /><a href="https://github.com/jonas1015/chacc-api/commits?author=jonas1015" title="Code">💻</a> <a href="#ideas-jonas1015" title="Ideas, Planning, & Feedback">🤔</a> <a href="#infra-jonas1015" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a> <a href="https://github.com/jonas1015/chacc-api/commits?author=jonas1015" title="Tests">⚠️</a> <a href="#design-jonas1015" title="Design">🎨</a> <a href="https://github.com/jonas1015/chacc-api/commits?author=jonas1015" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/bashirii"><img src="https://avatars.githubusercontent.com/u/104256265?v=4&size=100" width="100px" height="100px" alt="Bashiri Idd"/><br /><sub><b>Bashiri Idd</b></sub></a><br /><a href="https://github.com/jonas1015/chacc-api/commits?author=bashirii" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://linktr.ee/cleven02"><img src="https://avatars.githubusercontent.com/u/168540659?v=4&size=100" width="100px" height="100px" alt="cleven"/><br /><sub><b>cleven</b></sub></a><br /><a href="https://github.com/jonas1015/chacc-api/commits?author=cleven12" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/awodesigns-github"><img src="https://avatars.githubusercontent.com/u/135214966?v=4&size=100" width="100px" height="100px" alt="awodesigns-github"/><br /><sub><b>awodesigns-github</b></sub></a><br /><a href="https://github.com/jonas1015/chacc-api/commits?author=awodesigns-github" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://gody19.github.io/portfolio/"><img src="https://avatars.githubusercontent.com/u/163418534?v=4&size=100" width="100px" height="100px" alt="GODY OUWA"/><br /><sub><b>GODY OUWA</b></sub></a><br /><a href="https://github.com/jonas1015/chacc-api/commits?author=Gody19" title="Code">💻</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->
