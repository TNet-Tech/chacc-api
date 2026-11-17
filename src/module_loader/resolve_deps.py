"""Deprecated entry point, kept for custom Docker entrypoints that still call it.

The official entrypoint no longer resolves dependencies: the server checks module
packages itself at boot (see ``src/module_packages.py``). This runs
``chacc deps sync`` instead.

Usage:
    python -m src.module_loader.resolve_deps
"""

import sys


def main() -> int:
    from chacc_cli.deps import run_deps

    print("src.module_loader.resolve_deps is deprecated: use `chacc deps sync`.", file=sys.stderr)
    return run_deps("sync")


if __name__ == "__main__":
    sys.exit(main())
