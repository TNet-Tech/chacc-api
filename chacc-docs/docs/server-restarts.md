# Automatic Restarts

Module changes take effect after a server restart. You can trigger one remotely.

With a deploy:

```bash
chacc deploy my_module.chacc --restart
```

Or on its own:

```bash
curl -X POST http://localhost:8085/api/system/restart \
     -H "Authorization: Bearer <token>"
```

| Status | Meaning |
| --- | --- |
| `202` | Restart scheduled. |
| `401` | Authentication is required. |
| `409` | The server was not started with `chacc run server`. Restart it manually. |

Requests in progress are allowed to finish first. The server is usually back
within a few seconds.

## Requirements

Start the server with `chacc run server` (with or without `--dev`). The
production Docker image already does. Servers started with bare `uvicorn` return
`409`, including `docker-compose.dev.yml`.

## Docker

The restart happens inside the container, so the container keeps running.

- If a module fails with an import error after a restart, run
  `docker restart chacc-api` to install its packages.
- With plain `docker run`, pass `--stop-timeout 40` so requests can finish on
  `docker stop`. The Compose file already sets this.
- With several replicas, restart them through your orchestrator. The endpoint
  only reaches one.

## Settings

| Variable | Default | Description |
| --- | --- | --- |
| `CHACC_GRACEFUL_SHUTDOWN_TIMEOUT` | `30` | Seconds requests get to finish. |
| `CHACC_DEPLOY_RESTART_TIMEOUT` | `180` | Seconds `chacc deploy --restart` waits. |

## If something goes wrong

- A module that fails to load is logged and skipped. The server still starts.
- If the server cannot start at all, such as when the port is taken, it stays
  down until you fix the cause. Check the logs.
