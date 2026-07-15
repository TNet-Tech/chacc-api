# Core API

ChaCC API includes a small set of built-in endpoints for service discovery,
health checks, and module lifecycle management. Additional endpoints are mounted
by modules.

## Root

```http
GET /
```

Returns a welcome message and points users to the FastAPI documentation.

```json
{
  "message": "Welcome to the ChaCC API Backbone! Check /docs for API modules."
}
```

## Health checks

### Basic health

```http
GET /health
```

```json
{
  "status": "healthy",
  "mode": "development",
  "checks": {
    "api": "ok"
  }
}
```

### Readiness

```http
GET /health/ready
```

Runs a lightweight database query and reports whether the API and database are
ready.

```json
{
  "status": "healthy",
  "mode": "development",
  "checks": {
    "api": "ok",
    "database": "ok"
  }
}
```

### Liveness

```http
GET /health/live
```

```json
{
  "status": "alive",
  "mode": "development",
  "checks": {
    "process": "running"
  }
}
```

## Module management

Module management endpoints are available under the `Core` tag. When an
authentication module is loaded and registers `get_current_user`, these routes
require a bearer token. Without an authentication module, the core routes are
open.

### Install a module

```http
POST /modules/
```

Upload a `.chacc` archive as multipart form data.

```bash
curl -F "file=@billing.chacc" http://localhost:8085/modules/
```

Response:

```json
{
  "message": "Module 'billing' installed/updated successfully. Dependencies resolved. Please restart the API server to apply changes."
}
```

Validation:

- File name must end with `.chacc`.
- Archive must contain `module_meta.json`.
- `module_meta.json` must contain `name`.
- Dependencies are resolved before extraction.
- A server restart is required to activate the new module.

### List modules

```http
GET /modules/
```

```json
{
  "modules": [
    {
      "name": "authentication",
      "display_name": "Authentication Module",
      "version": "0.1.0",
      "author": "ChaCC",
      "description": "Authentication support.",
      "is_enabled": true,
      "base_path_prefix": "/auth"
    }
  ]
}
```

### Enable a module

```http
POST /modules/{module_name}/enable
```

Marks a module enabled in the database, resolves dependencies, extracts the
archive, and requires a restart to mount it.

### Disable a module

```http
POST /modules/{module_name}/disable
```

Marks a module disabled in the database, removes its extracted code directory,
and requires a restart to unmount it.

### Uninstall a module

```http
DELETE /modules/{module_name}/uninstall
```

Removes:

- The module archive from `.modules_installed/`.
- The extracted module directory from `.modules_loaded/`.
- The `ModuleRecord` from the database.

A restart is required to complete the uninstall.

## Rate limiting

The backbone installs a SlowAPI limiter and a custom handler for
`RateLimitExceeded`. Module routes can use `context.limiter` for throttling.

Example:

```python
@router.get("/status")
@context.limiter.limit("10/minute")
async def status():
    return {"status": "ok"}
```
