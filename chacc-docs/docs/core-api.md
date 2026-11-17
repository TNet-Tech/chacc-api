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
GET /api/health
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
GET /api/health/ready
```

Runs a lightweight database query and reports whether the API and database are
ready. Returns `200` when everything is ready and `503 Service Unavailable` (with
`"status": "unhealthy"`) when the database cannot be reached, so load balancers
and Kubernetes readiness probes stop sending traffic to the instance.

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
GET /api/health/live
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
POST /api/modules/
```

Upload a `.chacc` archive as multipart form data.

```bash
curl -F "file=@billing.chacc" http://localhost:8085/api/modules/
```

Response:

```json
{
  "message": "Module 'billing' installed/updated successfully. Restart the server to apply changes (POST /api/system/restart).",
  "warnings": []
}
```

Validation:

- File name must end with `.chacc`.
- Archive must contain `module_meta.json`.
- `module_meta.json` must contain `name`.
- The module's Python packages are installed into the packages folder before the
  archive is saved. If that fails nothing changes: `409` conflicting requirements,
  `422` requirements that can't be resolved, `503` package index unreachable.
- A server restart is required to activate the new module.

### List modules

```http
GET /api/modules/
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
POST /api/modules/{module_name}/enable
```

Marks a module enabled in the database, installs its Python packages (same errors
as upload), and requires a restart to mount it.

### Disable a module

```http
POST /api/modules/{module_name}/disable
```

Marks a module disabled in the database, removes its extracted code directory,
and requires a restart to unmount it.

### Uninstall a module

```http
DELETE /api/modules/{module_name}/uninstall
```

Removes:

- The module archive from `.modules_installed/`.
- The extracted module directory from `.modules_loaded/`.
- The `ModuleRecord` from the database.

A restart is required to complete the uninstall.

### Dependency graph

```text
GET /api/modules/graph
```

Returns the modules the server would load (installed archives in production,
`plugins/` in dev mode), the dependencies between them, which modules are
blocked, disabled or not installed, and the load order.

## Module console

Open `/console` in a browser to install, enable, disable and uninstall modules,
view the dependency graph and restart the server. When the authentication module
is loaded, the console asks you to log in.

## Server discovery

`GET /.well-known/chacc` is never prefixed. It returns the server's `api_prefix`,
a `boot_id` that changes on every restart, and `auth` (whether core routes need a
login, and the login path).

## Restart the server

```http
POST /api/system/restart
```

Applies module changes. Returns `202`, or `409` if the server was not started
with `chacc run server`. Like the module routes, it requires a login when the
authentication module is loaded. See [Automatic Restarts](server-restarts.md).

## Rate limiting

Routes are limited only when they use `rate_limit` from `chacc_api.rate_limit`
(see [Rate limiting](modules.md#rate-limiting)). Over the limit, the client gets
`429` with a `Retry-After` header:

```json
{"detail": "Too many requests. You have exceeded the rate limit of 10 per 1 minute."}
```

Clients are counted by IP. Counts are kept in memory unless
`RATE_LIMIT_STORAGE_URI` points to Redis. See [Configuration](configuration.md#rate-limiting).
