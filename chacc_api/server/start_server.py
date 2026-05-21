#!/usr/bin/env python3
"""
Safe server startup script that prevents auto-reloader loops.
Must NOT be run in production with development-mode settings.
"""

import os
import sys

os.environ["CHACC_DEV_MODE"] = "false"

from chacc_api.utils import LogLevels, configure_logging

chacc_logger = configure_logging(log_level=LogLevels.INFO)


def start_server(_logger=None):
    """Start the server without auto-reload, honouring CLI flags via env vars."""
    _log = _logger
    host = os.environ.get("CHACC_HOST", "0.0.0.0")
    port = int(os.environ.get("CHACC_PORT", "8085"))
    debug = os.environ.get("CHACC_DEBUG", "false").lower() in ("true", "1", "yes")

    if debug:
        from chacc_api.utils import LogLevels as _LL

        _log = configure_logging(log_level=_LL.DEBUG)
    elif _log is None:
        _log = configure_logging(log_level=LogLevels.INFO)

    _log.info(
        f"Starting server at {host}:{port} (reload=False, debug={debug})"
    )

    try:
        import uvicorn

        uvicorn.run("main:app", host=host, port=port, reload=False)
    except Exception as e:
        _log.error(f"❌ Error starting server: {e}")
        sys.exit(1)


def main():
    """Main startup sequence."""
    chacc_logger.info("=" * 60)
    chacc_logger.info("Starting ChaCC API Server (Production Mode)")
    chacc_logger.info("=" * 60)
    chacc_logger.info("🟢 Starting server...")
    start_server(chacc_logger)


if __name__ == "__main__":
    main()
