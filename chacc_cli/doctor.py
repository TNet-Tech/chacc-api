"""
`chacc doctor` - diagnose a ChaCC API setup and explain how to fix problems.

Deliberately standard-library only and free of imports from ``src`` so it keeps
working when the configuration is broken (``src.constants`` creates directories and
reads settings at import time, which is exactly what we want to check safely).
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

OK = "ok"
WARN = "warn"
FAIL = "fail"

MIN_PYTHON = (3, 10)
MIN_SECRET_LENGTH = 32
# Kept in sync with src/env_validator.py
INSECURE_SECRET_PATTERNS = (
    r"^dev-",
    r"^test-",
    r"^your-",
    r"^change.*in.*production",
    r"^default$",
    r"^123456",
    r"^(.)\1+$",
)
_TRUE = {"1", "true", "yes", "on"}


@dataclass
class Check:
    """Result of a single diagnostic check."""

    name: str
    status: str
    message: str
    hint: str = ""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUE


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines (comments, blank lines and simple quotes supported)."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key:
            values[key] = value
    return values


def load_settings(cwd: Path, environ: Mapping[str, str]) -> dict[str, str]:
    """Merge ``.env`` (if any) with the environment; real env vars win, as in decouple."""
    settings: dict[str, str] = {}
    env_file = cwd / ".env"
    if env_file.is_file():
        try:
            settings.update(parse_dotenv(env_file.read_text(encoding="utf-8")))
        except OSError:
            pass
    settings.update(environ)
    return settings


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", port)) != 0


def _can_connect(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _dir_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".chacc_doctor_probe"
        probe.write_text("x")
        probe.unlink()
        return True
    except OSError:
        return False


def check_python(version: tuple[int, ...] = tuple(sys.version_info[:3])) -> Check:
    found = ".".join(str(p) for p in version[:3])
    if tuple(version[:2]) >= MIN_PYTHON:
        return Check("Python version", OK, f"Python {found}")
    return Check(
        "Python version",
        FAIL,
        f"Python {found} is too old (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)",
        "Install a newer Python, then recreate your virtual environment.",
    )


def check_env_file(cwd: Path) -> Check:
    if (cwd / ".env").is_file():
        return Check(".env file", OK, "Found .env in the current directory")
    return Check(
        ".env file",
        WARN,
        "No .env file in the current directory",
        "Run `cp .env.sample .env` (ChaCC creates .env.sample on first start) "
        "or export the variables in your shell.",
    )


def check_secret_key(settings: Mapping[str, str], dev_mode: bool) -> Check:
    secret = settings.get("SECRET_KEY", "")
    generate = 'python -c "import secrets; print(secrets.token_urlsafe(48))"'
    if not secret:
        status = WARN if dev_mode else FAIL
        return Check(
            "SECRET_KEY",
            status,
            "SECRET_KEY is not set",
            f"Generate one with: {generate}",
        )
    problems = []
    if len(secret) < MIN_SECRET_LENGTH:
        problems.append(f"only {len(secret)} characters (need {MIN_SECRET_LENGTH}+)")
    if any(re.search(p, secret.lower()) for p in INSECURE_SECRET_PATTERNS):
        problems.append("looks like a placeholder value")
    if not problems:
        return Check("SECRET_KEY", OK, "SECRET_KEY looks strong")
    status = WARN if dev_mode else FAIL
    return Check(
        "SECRET_KEY",
        status,
        "SECRET_KEY is weak: " + ", ".join(problems),
        f"Generate one with: {generate}",
    )


def check_production_flags(settings: Mapping[str, str], dev_mode: bool) -> Check:
    risky = [
        name
        for name in ("ENABLE_PLUGIN_HOT_RELOAD", "PLUGIN_AUTO_DISCOVERY")
        if _truthy(settings.get(name))
    ]
    if dev_mode or not risky:
        return Check("Production flags", OK, "No development-only flags enabled in production")
    return Check(
        "Production flags",
        FAIL,
        f"{', '.join(risky)} must be disabled in production",
        "Set them to false, or run with CHACC_DEV_MODE=true for local development.",
    )


def check_database(
    settings: Mapping[str, str],
    cwd: Path,
    can_connect: Callable[[str, int], bool] = _can_connect,
) -> Check:
    engine = settings.get("DATABASE_ENGINE", "sqlite").lower()
    if "postgres" in engine:
        host = settings.get("DATABASE_HOST", "localhost")
        try:
            port = int(settings.get("DATABASE_PORT", "5432"))
        except ValueError:
            return Check("Database", FAIL, "DATABASE_PORT is not a number", "Use e.g. 5432.")
        missing = [
            k
            for k in ("DATABASE_USER", "DATABASE_PASSWORD", "DATABASE_NAME")
            if not settings.get(k)
        ]
        if missing:
            return Check(
                "Database",
                FAIL,
                f"Missing PostgreSQL settings: {', '.join(missing)}",
                "Set them in .env (see .env.sample).",
            )
        if can_connect(host, port):
            return Check("Database", OK, f"PostgreSQL reachable at {host}:{port}")
        return Check(
            "Database",
            FAIL,
            f"Cannot reach PostgreSQL at {host}:{port}",
            "Is PostgreSQL running and DATABASE_HOST/DATABASE_PORT correct?",
        )
    db_dir = Path(settings.get("SQLITE_DATABASE_PATH", str(cwd)))
    if _dir_writable(db_dir):
        return Check("Database", OK, f"SQLite directory is writable ({db_dir})")
    return Check(
        "Database",
        FAIL,
        f"Cannot write to SQLite directory {db_dir}",
        "Fix permissions or set SQLITE_DATABASE_PATH to a writable folder.",
    )


def check_redis(
    settings: Mapping[str, str],
    can_connect: Callable[[str, int], bool] = _can_connect,
) -> Check:
    if not _truthy(settings.get("REDIS_ENABLED")):
        return Check("Redis", OK, "Redis is disabled (optional)")
    host = settings.get("REDIS_HOST", "localhost")
    try:
        port = int(settings.get("REDIS_PORT", "6379"))
    except ValueError:
        return Check("Redis", FAIL, "REDIS_PORT is not a number", "Use e.g. 6379.")
    if can_connect(host, port):
        return Check("Redis", OK, f"Redis reachable at {host}:{port}")
    return Check(
        "Redis",
        WARN,
        f"Cannot reach Redis at {host}:{port} (ChaCC will continue without it)",
        "Start Redis or set REDIS_ENABLED=false.",
    )


def check_port(host: str, port: int, port_is_free: Callable[[str, int], bool] = _port_is_free):
    if port_is_free(host, port):
        return Check("Server port", OK, f"Port {port} is free")
    return Check(
        "Server port",
        WARN,
        f"Port {port} is already in use",
        f"Stop the other process or run `chacc run server --port {port + 1}`.",
    )


def check_directories(settings: Mapping[str, str], cwd: Path) -> Check:
    names = {
        "PLUGINS_DIR": "plugins",
        "MODULES_INSTALLED_DIR": ".modules_installed",
        "MODULES_LOADED_DIR": ".modules_loaded",
    }
    bad = [
        str(cwd / settings.get(var, default))
        for var, default in names.items()
        if not _dir_writable(cwd / settings.get(var, default))
    ]
    if not bad:
        return Check("Module folders", OK, "Module folders are writable")
    return Check(
        "Module folders",
        FAIL,
        f"Cannot write to: {', '.join(bad)}",
        "Fix folder permissions or run from a directory you own.",
    )


def run_checks(
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
    dev_mode: bool | None = None,
    host: str = "0.0.0.0",
    port: int = 8085,
) -> list[Check]:
    """Run every check and return the results (no printing, no exiting)."""
    cwd = cwd or Path.cwd()
    settings = load_settings(cwd, os.environ if environ is None else environ)
    if dev_mode is None:
        dev_mode = _truthy(settings.get("CHACC_DEV_MODE"))
    return [
        check_python(),
        check_env_file(cwd),
        check_secret_key(settings, dev_mode),
        check_production_flags(settings, dev_mode),
        check_database(settings, cwd),
        check_redis(settings),
        check_directories(settings, cwd),
        check_port(host, port),
    ]


def exit_code(results: list[Check], strict: bool = False) -> int:
    """1 if any check failed (or warned, with ``strict``), else 0."""
    bad = {FAIL, WARN} if strict else {FAIL}
    return 1 if any(r.status in bad for r in results) else 0


def format_report(results: list[Check], use_color: bool = False) -> str:
    icons = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}
    colors = {OK: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m"}
    lines = ["ChaCC doctor", ""]
    for r in results:
        icon = icons[r.status]
        if use_color:
            icon = f"{colors[r.status]}{icon}\033[0m"
        lines.append(f"{icon} {r.name}: {r.message}")
        if r.hint and r.status != OK:
            lines.append(f"       -> {r.hint}")
    fails = sum(r.status == FAIL for r in results)
    warns = sum(r.status == WARN for r in results)
    lines.append("")
    if fails:
        lines.append(f"{fails} problem(s) need fixing before you start the server.")
    elif warns:
        lines.append(f"Looks usable, with {warns} warning(s).")
    else:
        lines.append("Everything looks good. Start the server with: chacc run server --dev")
    return "\n".join(lines)


def run_doctor(
    as_json: bool = False,
    strict: bool = False,
    dev: bool = False,
    host: str = "0.0.0.0",
    port: int = 8085,
) -> int:
    """CLI entry point. Prints the report and returns the process exit code."""
    results = run_checks(dev_mode=True if dev else None, host=host, port=port)
    if as_json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        print(format_report(results, use_color=sys.stdout.isatty()))
    return exit_code(results, strict=strict)
