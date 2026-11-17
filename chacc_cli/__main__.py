"""
ChaCC CLI - Command Line Interface for ChaCC API module management.
"""

import argparse
import os
import subprocess
import sys

_RED = "\033[31m"
_YELLOW = "\033[33m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _color(text: str, ansi: str) -> str:
    return f"{ansi}{text}{_RESET}" if sys.stdout.isatty() else text


_CLEAN_EXITS = (0, -2, -15, 130, 143)


def _supervise_server(cmd: list[str], env: dict[str, str]) -> int:
    """
    Run the server and start it again whenever it asks to be restarted.

    The server exits with ``RESTART_EXIT_CODE`` after ``POST /system/restart``
    (see ``src/system.py``); any other exit ends supervision.

    Stop signals are forwarded to the server so it shuts down gracefully. This
    matters in Docker, where the supervisor is PID 1: ``docker stop`` sends
    SIGTERM to PID 1 only, and PID 1 ignores signals it has no handler for.

    - first SIGINT/SIGTERM: forward SIGTERM (graceful) and wait;
    - second one: kill the server immediately.

    SIGTERM is forwarded even for Ctrl+C because the terminal already sent
    SIGINT to the server, and a second SIGINT would make uvicorn force-quit.
    """
    import signal

    from src.lifecycle import RESTART_EXIT_CODE, SUPERVISED_ENV

    env = {**env, SUPERVISED_ENV: "1"}
    env.pop("CHACC_SERVER_ROOT_PID", None)
    state: dict = {"child": None, "stopping": False}

    def on_stop_signal(signum, frame):
        child = state["child"]
        if state["stopping"]:
            if child is not None and child.poll() is None:
                print(_color("\nForcing ChaCC server to stop...", _YELLOW), flush=True)
                child.kill()
            return
        state["stopping"] = True
        print(_color("\nShutting down ChaCC server...", _YELLOW), flush=True)
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGTERM)

    stop_signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        stop_signals.append(signal.SIGHUP)
    previous = {sig: signal.signal(sig, on_stop_signal) for sig in stop_signals}

    restarts = 0
    try:
        while not state["stopping"]:
            child = subprocess.Popen(cmd, env=env, cwd=os.getcwd())
            state["child"] = child
            returncode = child.wait()
            if state["stopping"]:
                break
            if returncode != RESTART_EXIT_CODE:
                return 0 if returncode in _CLEAN_EXITS else returncode
            restarts += 1
            print(
                _color(f"\nRestarting ChaCC server (restart #{restarts})...", _YELLOW), flush=True
            )
        returncode = state["child"].wait() if state["child"] else 0
        return 0 if returncode in _CLEAN_EXITS else returncode
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    """
    Main CLI entry point.
    """
    parser = argparse.ArgumentParser(
        prog="chacc",
        description="ChaCC API CLI for module scaffolding, packaging, and deployment.\n\n"
        "Deployment requires environment variables:\n"
        "  CHACC_DEPLOY_URL=http://your-api-server.com\n"
        "  CHACC_DEPLOY_API_KEY=optional-bearer-token\n"
        "  CHACC_DEPLOY_USERNAME / CHACC_DEPLOY_PASSWORD=optional, for non-interactive login\n"
        "  CHACC_DEPLOY_AUTH_PATH=/authentication\n"
        "  CHACC_DEPLOY_TIMEOUT=600 (seconds to wait for the server response)",
    )
    parser.add_argument(
        "--version", action="store_true", help="Show the installed ChaCC API version and exit."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    doctor_parser = subparsers.add_parser(
        "doctor", help="Check your setup and get plain-language fixes for any problems."
    )
    doctor_parser.add_argument("--dev", action="store_true", help="Check as a development setup.")
    doctor_parser.add_argument("--json", action="store_true", help="Print results as JSON.")
    doctor_parser.add_argument(
        "--strict", action="store_true", help="Exit with an error on warnings too (for CI)."
    )
    doctor_parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to check.")
    doctor_parser.add_argument("--port", type=int, default=8085, help="Port to check.")

    scaffold_parser = subparsers.add_parser("create", help="Create a new ChaCC API module.")
    scaffold_parser.add_argument(
        "module_name",
        type=str,
        help="The name of the module to create (e.g., 'my_awesome_module').",
    )
    scaffold_parser.add_argument(
        "--output-dir",
        type=str,
        default="plugins",
        help="The directory where the new module will be created. Defaults to 'plugins/'.",
    )
    scaffold_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing module if it exists."
    )

    build_parser = subparsers.add_parser(
        "build", help="Build an ChaCC API module into an .chacc package."
    )
    build_parser.add_argument(
        "module_source_dir",
        type=str,
        help="The path to the module's source directory (e.g., 'plugins/my_awesome_module').",
    )
    build_parser.add_argument(
        "--output-filename",
        type=str,
        default=None,
        help="Optional: The name of the output .chacc file. Defaults to '<module_name>.chacc'.",
    )

    from .commands import build_install_parser

    build_install_parser(subparsers)

    deploy_parser = subparsers.add_parser(
        "deploy",
        help="Deploy an .chacc module to a remote ChaCC API instance.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    deploy_parser.add_argument(
        "chacc_file",
        type=str,
        help="The path to the .chacc file to deploy (e.g., 'my_module.chacc').",
    )
    deploy_parser.add_argument(
        "--restart",
        action="store_true",
        help=(
            "Restart the server after a successful deploy and wait until it is back "
            "(requires the server to run via 'chacc run server')."
        ),
    )
    deploy_parser.epilog = (
        "If the server requires authentication (401), you are prompted for a\n"
        "username and password unless credentials are provided via env.\n\n"
        "Environment variables:\n"
        "  CHACC_DEPLOY_URL=http://your-api-server.com\n"
        "  CHACC_DEPLOY_API_KEY=optional-bearer-token\n"
        "  CHACC_DEPLOY_USERNAME / CHACC_DEPLOY_PASSWORD=optional, for non-interactive login\n"
        "  CHACC_DEPLOY_AUTH_PATH=/authentication\n"
        "  CHACC_DEPLOY_TIMEOUT=600 (seconds to wait for the server response)\n"
        "  CHACC_DEPLOY_RESTART_TIMEOUT=180 (seconds to wait for --restart)"
    )

    server_cmd_parser = subparsers.add_parser("server", help="Run the ChaCC development server.")
    server_cmd_parser.add_argument(
        "--modules-dir",
        type=str,
        default="plugins",
        help="Directory containing ChaCC modules. Defaults to 'plugins/'.",
    )
    server_cmd_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server to. Defaults to '0.0.0.0'.",
    )
    server_cmd_parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind the server to. Defaults to 8000."
    )
    server_cmd_parser.add_argument("--debug", action="store_true", help="Enable debug mode.")
    server_cmd_parser.add_argument(
        "--auto-reload", action="store_true", help="Enable auto-reload for development."
    )

    deps_parser = subparsers.add_parser(
        "deps", help="Check or install the Python packages of installed modules."
    )
    deps_parser.add_argument(
        "deps_action",
        choices=["check", "sync"],
        help="check: report what is installed (no network). "
        "sync: resolve and install what is missing (needs network).",
    )

    run_parser = subparsers.add_parser("run", help="Run the ChaCC server.")
    run_subparsers = run_parser.add_subparsers(dest="run_subcommand", help="Run subcommands")

    run_server_parser = run_subparsers.add_parser("server", help="Run the ChaCC server.")
    run_server_parser.add_argument(
        "--dev",
        action="store_true",
        help="Run in development mode with auto-reload (uses uvicorn_config.py).",
    )
    run_server_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server to. Defaults to '0.0.0.0'.",
    )
    run_server_parser.add_argument(
        "--port", type=int, default=8085, help="Port to bind the server to. Defaults to 8085."
    )
    run_server_parser.add_argument("--debug", action="store_true", help="Enable debug mode.")

    run_server_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed logs (DEBUG level) for this invocation.",
    )

    args = parser.parse_args()

    if args.version:
        from importlib.metadata import PackageNotFoundError, version

        try:
            print(f"chacc-api {version('chacc-api')}")
        except PackageNotFoundError:
            print("chacc-api (version unknown: not installed as a package)")
        sys.exit(0)

    if args.command == "doctor":
        from .doctor import run_doctor

        sys.exit(
            run_doctor(
                as_json=args.json,
                strict=args.strict,
                dev=args.dev,
                host=args.host,
                port=args.port,
            )
        )

    if args.command == "deps":
        from .deps import run_deps

        sys.exit(run_deps(args.deps_action))

    from .commands import (
        build_install_parser,
        build_module_chacc,
        create_module_scaffold,
        deploy_module,
        install_module,
    )

    if args.command == "create":
        create_module_scaffold(args.module_name, args.output_dir, args.force)
    elif args.command == "install":
        from chacc_cli.installer.paths import PathError
        from chacc_cli.installer.source import SourceError
        from chacc_cli.installer.validate import ValidationError

        try:
            install_module(
                source=args.source,
                ref=args.ref,
                dev=args.dev,
                force=args.force,
                depth=args.depth,
                full=args.full,
                single_branch=args.single_branch,
                token_env=args.token_env,
                quiet=args.quiet,
            )
        except (SourceError, ValidationError, PathError) as exc:
            # The progress stepper has already printed [FAIL] with the message.
            msg = _color(f"\nInstall failed: {exc}", _BOLD + _RED)
            print(msg)
            sys.exit(1)
        else:
            sys.exit(0)
    elif args.command == "build":
        build_module_chacc(args.module_source_dir, args.output_filename)
    elif args.command == "deploy":
        sys.exit(0 if deploy_module(args.chacc_file, restart=args.restart) else 1)

    elif args.command == "run":
        if args.run_subcommand == "server":
            from pathlib import Path

            cli_dir = Path(__file__).resolve().parent.parent
            project_root = cli_dir
            package_dir = cli_dir / "chacc_api" / "server"

            env = os.environ.copy()

            env["PYTHONPATH"] = str(str(project_root) + os.pathsep + env.get("PYTHONPATH", ""))

            env["CHACC_HOST"] = args.host
            env["CHACC_PORT"] = str(args.port)

            if args.verbose:
                env["CHACC_VERBOSE"] = "true"
            else:
                env.pop("CHACC_VERBOSE", None)

            if args.dev:
                env["CHACC_DEV_MODE"] = "true"

                if args.debug:
                    env["CHACC_DEBUG"] = "true"
                config_path = package_dir / "uvicorn_config.py"
                cmd = [sys.executable, str(config_path)]
            else:
                server_path = package_dir / "start_server.py"
                cmd = [sys.executable, str(server_path)]

            sys.exit(_supervise_server(cmd, env))
        elif args.run_subcommand is None:
            msg = _color(
                "Error: 'run' command requires a subcommand. Use 'chacc run server'.", _YELLOW
            )
            print(msg)
            run_parser.print_help()
            sys.exit(1)
        else:
            run_parser.print_help()
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
