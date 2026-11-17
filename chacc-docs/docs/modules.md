# Modules

Modules are the main extension mechanism in ChaCC API. A module contributes
models, routes, services, configuration, and tests while the backbone handles
startup, migration, dependency resolution, and mounting.

## Module layout

```text
my_module/
  module_meta.json
  requirements.txt
  my_module_src/
    __init__.py
    main.py
    models.py
    routes.py
    context_factory.py
    run_tests.py
    tests/
      __init__.py
      test_module.py
  README.md
  .gitignore
```

## `module_meta.json`

| Field | Required | Description |
| --- | --- | --- |
| `name` | Yes | Machine-readable module name. |
| `display_name` | No | Human-readable name shown in module records. |
| `version` | No | Module version. |
| `author` | No | Author or organization. |
| `description` | No | Module description. |
| `entry_point` | Yes | Python path to setup function, for example `my_module_src.main:setup_plugin`. |
| `test_entry_point` | No | Python path to the module's test runner, set by `chacc create`. |
| `base_path_prefix` | No | Module path, for example `/billing`. Always mounted under the server's `API_PREFIX` (default `/api`), so `/billing` is served at `/api/billing`. |
| `tags` | No | FastAPI documentation tags. |
| `dependencies_file` | No | Requirements file name, usually `requirements.txt`. |
| `module_dependencies` | No | Other ChaCC modules this module needs. See [Module dependencies](#module-dependencies). |
| `required_chacc_version` | No | Minimum ChaCC version. |
| `license` | No | Module license. |
| `homepage` | No | Module homepage. |

## Setup function

A module entry point must expose a callable setup function.

```python
from fastapi import APIRouter
from chacc_api import BackboneContext


def setup_plugin(context: BackboneContext):
    router = APIRouter(prefix="/items", tags=["Items"])

    @router.get("/")
    async def list_items():
        return {"items": []}

    return router
```

The setup function may be synchronous or asynchronous. It receives
`BackboneContext` and must return a FastAPI `APIRouter`.

## Models

Models should inherit from `ChaCCBaseModel`. The legacy `@register_model`
decorator is retained as a backward-compatible no-op and should not be used in
new code.

```python
from chacc_api import ChaCCBaseModel
from sqlalchemy import Column, String


class Item(ChaCCBaseModel):
    __tablename__ = "items"
    name = Column(String, nullable=False)
```

`ChaCCBaseModel` adds:

| Field | Type | Purpose |
| --- | --- | --- |
| `id` | `Integer` | Primary key. |
| `uuid` | `GUID` | Cross-database UUID value, defaults to `uuid7`. |
| `created_at` | `DateTime` | Creation timestamp. |
| `updated_at` | `DateTime` | Last update timestamp. |
| `deleted_at` | `DateTime` | Soft-delete timestamp. |

## Database sessions

All database helpers come from `chacc_api.database`. Prefer the async session
(`AsyncSession`): it doesn't block the server while it waits for the database.
Each helper has a synchronous twin (`get_db`, `session`, `with_session`).

The rule: the code that opens a session closes it, when its work ends. The
helpers do that for you, also on errors.

**In routes**, use the dependency. FastAPI closes the session after the response:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from chacc_api.database import get_async_db

router = APIRouter()


@router.get("/items")
async def list_items(db: AsyncSession = Depends(get_async_db)):
    items = (await db.execute(select(Item))).scalars().all()
    return [item.name for item in items]
```

**In a block of code** (startup, background tasks):

```python
from chacc_api.database import async_session

async with async_session() as db:
    items = (await db.execute(select(Item))).scalars().all()
```

**In functions and service classes**, decorate with `with_async_session`. Each
call gets its own session as the keyword argument `db`; callers don't pass one:

```python
from chacc_api.database import with_async_session


class ItemService:
    @with_async_session
    async def rename(self, item_id, name, *, db):
        item = await db.get(Item, item_id)
        item.name = name
        await db.commit()


await ItemService().rename(1, "new")
```

To run several calls in one transaction, pass your session: `await
service.rename(1, "new", db=db)`. That session is then left open for you to close.

**A class may keep a session it receives** (for example a repository built per
request), as long as it doesn't outlive the request or block that opened it and
doesn't close it itself.

Avoid:

- Returning a session, or storing one on a long-lived service (created in
  `setup_plugin` or registered with `context.register_service()`). An
  `AsyncSession` can't be shared by concurrent requests.
- `db = await anext(get_async_db())`. Nothing closes that session except the
  garbage collector, sometimes in the middle of a query (`CLOSE FAILED ...
  _connection_for_bind() is already in progress`), and the connection pool runs
  out under load.

Modules made with `chacc create` can also import `get_async_db` and `get_db`
from their own `context_factory.py`; they are the same functions.

!!! note "Deprecated: `context.get_db` and `context.get_db_async`"
    They still work in this release but log a deprecation warning. Replace
    `Depends(context.get_db_async)` with `Depends(get_async_db)` and
    `Depends(context.get_db)` with `Depends(get_db)` from `chacc_api.database`.

## Rate limiting

Limit how often a route can be called with `rate_limit`, placed **under** the
route decorator:

```python
from chacc_api.rate_limit import rate_limit


@router.get("/status")
@rate_limit("10/minute")
async def status():
    return {"status": "ok"}
```

- Limits look like `"10/minute"`, `"5/second"` or several at once:
  `"5/second;100/hour"`. Stacked decorators all apply.
- Clients are counted by IP. To count by something else, pass a function of the
  request: `@rate_limit("100/hour", key=lambda request: request.headers["x-api-key"])`.
- Over the limit, the client gets `429` with a `Retry-After` header.
- The route doesn't need a `request` parameter.
- Routes without `rate_limit` are not limited.

Counting is set up for the whole server (in memory or Redis, see
[Configuration](configuration.md#rate-limiting)). `context.limiter` is the same
limiter, for SlowAPI features such as shared limits.

## Services

Modules can share behavior through `BackboneContext`.

```python
def verify_token(token: str):
    return token == "example"


def setup_plugin(context):
    context.register_service("token_verifier", verify_token)
    return router
```

Another module can retrieve it:

```python
verifier = context.get_service("token_verifier")
```

## Dependencies

Put Python dependencies in `requirements.txt`. ChaCC resolves and installs them
when the module is uploaded or enabled, before the module is saved, so a failure
changes nothing.

```text
requests
qrcode>=7.4
```

- Core packages (FastAPI, SQLAlchemy, Pydantic and the rest of ChaCC's own
  dependencies) can't be changed by a module. Requirements that only fit another
  core version are refused.
- In production, packages are installed into `.chacc_packages/` and stay there
  across restarts. See [Running without network](deployment.md#running-without-network).
- Upload or enable errors: `409` conflicting requirements, `422` requirements that
  can't be resolved, `503` the package index can't be reached.

## Module dependencies

List the other ChaCC modules your module uses in `module_meta.json`:

```json
"module_dependencies": {
  "required": ["chacc_authentication"],
  "optional": ["chacc_file_manager"]
}
```

- **required**: the module can't work without these, for example because its
  models have foreign keys to their tables.
- **optional**: the module works without these, with fewer features.

ChaCC never installs modules for you. A module is checked against the modules in
`plugins/` in dev mode, and against installed modules in production.

| When | Required module missing | Optional module missing |
| --- | --- | --- |
| `chacc install`, `chacc deploy`, enable | Refused, with the missing modules listed. | Installed, with a warning. |
| Server start | Module is skipped and listed in the log. | Module loads, and a warning is logged. |

Install the missing modules yourself, then restart. Modules always load after
the modules they depend on.

## Build and deploy

```bash
chacc create my_module
chacc run server --dev
chacc build plugins/my_module
chacc deploy my_module.chacc
```

The build command creates a ZIP archive named after the module unless an output
filename is provided.

## Development mode vs production mode

| Mode | Source directory | Behavior |
| --- | --- | --- |
| Development | `plugins/` | Loads modules from source directories with optional hot reload. |
| Production | `.modules_installed/` | Loads enabled modules from extracted archives. |

## Best practices

- Keep module names lowercase with underscores.
- Use one `APIRouter` per module.
- Put database models in importable Python files so model discovery can find
  `ChaCCBaseModel` subclasses.
- Avoid circular imports by using `context.get_service()` instead of direct
  module imports.
- Store module-specific secrets as `{MODULE_NAME}_{KEY}` in `.env`.
- Restart the backbone after installing, enabling, disabling, or uninstalling a
  module.
- Failed module loads are automatically disabled in the database to prevent
  repeated startup crashes.
