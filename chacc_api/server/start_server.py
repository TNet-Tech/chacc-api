#!/usr/bin/env python3
"""
Safe server startup script that prevents auto-reloader loops.
"""

import sys

from chacc_api.utils import LogLevels, configure_logging

logger = configure_logging(log_level=LogLevels.INFO)


def start_server():
    """Start the server without auto-reload."""
    logger.info("Starting server without auto-reload...")

    try:
        import uvicorn

        uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
    except Exception as e:
        logger.error(f"❌ Error starting server: {e}")
        sys.exit(1)


def main():
    """Main startup sequence."""
    logger.info("=" * 60)
    logger.info("Starting ChaCC API Server (Safe Mode)")
    logger.info("=" * 60)

    logger.info("🟢 Starting server...")
    start_server()


if __name__ == "__main__":
    main()
