"""
Server lifecycle: restart without manual intervention.

How a restart works
-------------------
``chacc run server`` acts as a supervisor: it runs the server in a child
process and starts it again whenever the child exits with
:data:`RESTART_EXIT_CODE`.

``POST {API_PREFIX}/system/restart``:

1. refuses (409) unless the server runs under that supervisor, so a server
   started some other way (bare ``uvicorn``, a custom process manager) is never
   shut down without anything to bring it back;
2. writes a restart marker file and replies ``202 Accepted`` right away;
3. shortly after, sends SIGTERM to the server's root process. Uvicorn shuts
   down gracefully: it stops accepting connections, lets in-flight requests
   (e.g. a module install) finish, and runs the lifespan shutdown;
4. the launcher (``start_server.py`` / ``uvicorn_config.py``) sees the marker
   after ``uvicorn.run`` returns and exits with ``RESTART_EXIT_CODE``;
5. the supervisor starts a fresh process, which loads newly installed modules.

Each process gets a new :data:`BOOT_ID`, exposed via ``/.well-known/chacc``,
so clients can tell when the restart has actually completed.

The marker file (see :mod:`src.lifecycle`) is needed because, in ``--dev`` mode, the request is handled
in uvicorn's reload *worker*, while ``uvicorn.run`` returns in the parent.
"""

import asyncio
import os
import signal
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from src.lifecycle import SERVER_ROOT_PID_ENV, request_restart, restart_supported
from src.logger import configure_logging, get_default_log_level
from src.modules import get_current_user_optional

chacc_logger = configure_logging(log_level=get_default_log_level())

RESTART_DELAY_SECONDS = 0.5

BOOT_ID = uuid.uuid4().hex
STARTED_AT = time.time()

_restart_pending = False
_restart_task: asyncio.Task | None = None

system_router = APIRouter(tags=["Core"])


async def _signal_shutdown(root_pid: int) -> None:
    await asyncio.sleep(RESTART_DELAY_SECONDS)
    chacc_logger.info(f"Restart: sending SIGTERM to server process {root_pid}.")
    os.kill(root_pid, signal.SIGTERM)


def server_info() -> dict:
    return {
        "boot_id": BOOT_ID,
        "started_at": STARTED_AT,
        "restart_supported": restart_supported(),
        "restart_pending": _restart_pending,
    }


@system_router.post("/system/restart", status_code=status.HTTP_202_ACCEPTED)
async def restart_server_endpoint(
    current_user: object | None = Depends(get_current_user_optional),
):
    """
    Gracefully restart the server so installed/enabled/disabled modules take effect.

    Requires the server to be started with ``chacc run server`` (the supervisor).
    In-flight requests are allowed to finish. Poll ``/.well-known/chacc`` until
    ``boot_id`` changes to know the new process is up.
    """
    global _restart_pending, _restart_task

    if not restart_supported():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Automatic restart is unavailable: the server is not running under the "
                "ChaCC supervisor. Start it with 'chacc run server' or restart it manually."
            ),
        )
    if _restart_pending:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"message": "Restart already in progress.", "boot_id": BOOT_ID},
        )

    root_pid = int(os.environ[SERVER_ROOT_PID_ENV])
    request_restart(root_pid, BOOT_ID)
    _restart_pending = True
    _restart_task = asyncio.get_running_loop().create_task(_signal_shutdown(root_pid))
    chacc_logger.info("Server restart requested via API.")
    return {
        "message": "Restart scheduled. The server will be back shortly.",
        "boot_id": BOOT_ID,
    }
