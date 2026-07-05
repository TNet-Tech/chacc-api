# CLI

The `chacc` command manages module development, packaging, deployment, and
server startup.

## Create a module

```bash
chacc create my_module
```

Creates a module scaffold in `plugins/my_module/`.

Options:

| Option | Description |
| --- | --- |
| `--output-dir` | Output directory. Defaults to `plugins`. |
| `--force` | Overwrite an existing module directory. |

## Build a module

```bash
chacc build plugins/my_module
```

Builds `my_module.chacc` from the source directory.

Options:

| Option | Description |
| --- | --- |
| `--output-filename` | Custom output archive name. |

The source directory must contain `module_meta.json`.

## Deploy a module

```bash
chacc deploy my_module.chacc
```

Uploads the module to the configured ChaCC API instance.

Required environment variable:

```bash
CHACC_DEPLOY_URL=http://localhost:8085
```

Optional environment variables (Still under development):

```bash
CHACC_DEPLOY_API_KEY=optional-token
CHACC_DEPLOY_TIMEOUT=30
```

## Run the server

Development server:

```bash
chacc run server --dev
```

Production server:

```bash
chacc run server
```

Options:

| Option | Description |
| --- | --- |
| `--dev` | Run in development mode with auto-reload. |
| `--host` | Host to bind. Defaults to `0.0.0.0`. |
| `--port` | Port to bind. Defaults to `8085`. |
| `-v` / `--verbose` | Enable verbose logging (`CHACC_VERBOSE=true`). The flag is passed to the server subprocess, so startup logs and application logs use `INFO` level. |
| `--debug` | Enable debug logging (`CHACC_DEBUG=true` in development mode). |

## Legacy server command

```bash
chacc server --host 0.0.0.0 --port 8085
```

This command is retained for compatibility. Prefer `chacc run server`.

## Typical workflow

```bash
chacc create billing
cd plugins/billing
# edit module_meta.json, models.py, routes.py, and tests
chacc run server --dev
chacc build plugins/billing
chacc deploy billing.chacc
```

## Module name rules

Module names:

- Cannot be empty.
- Cannot start with a number.
- May contain letters, numbers, underscores, hyphens, and spaces.
- Are normalized to lowercase with underscores.
