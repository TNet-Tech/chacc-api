"""
Progress UX for ``chacc install``.

Each phase of the install pipeline is wrapped in a small context manager
that prints a visible ``->`` / ``[OK]`` / ``[FAIL]`` marker and an optional
one-line detail. Output is plain ``print()`` so it shows up regardless of
log level and reads cleanly in CI logs and pipes.

Honors ``--quiet``: when quiet, the stepper is silent (only ``final()`` is
still printed because callers need to confirm success/failure).
"""

from __future__ import annotations

from contextlib import contextmanager

_ARROW = "->"
_OK = "[OK]"
_FAIL = "[FAIL]"


_quiet_flag: dict[str, bool] = {}


def set_quiet(value: bool) -> None:
    """Toggle global quiet mode."""
    _quiet_flag["value"] = bool(value)


def get_quiet() -> bool:
    return bool(_quiet_flag.get("value", False))


def _print(line: str) -> None:
    print(line, flush=True)


@contextmanager
def step(message: str, detail: str = ""):
    """
    Print ``-> message  detail`` on entry, ``[OK] message`` on success,
    and ``[FAIL] message: <error>`` on failure (then re-raise).

    Honors :func:`set_quiet`: when quiet, the stepper is silent but still
    re-raises on failure so callers see the same control flow.

    Usage::

        with step("Resolving source", detail=url):
            resolved = source_mod.resolve(...)
    """
    if not get_quiet():
        suffix = f"  ({detail})" if detail else ""
        _print(f"{_ARROW} {message}{suffix}")
    try:
        yield
    except Exception as exc:
        if not get_quiet():
            _print(f"{_FAIL} {message}: {exc}")
        raise
    else:
        if not get_quiet():
            _print(f"{_OK} {message}")


def info(message: str) -> None:
    """Print a non-step informational line. Suppressed when --quiet."""
    if not get_quiet():
        _print(f"   {message}")


def warn(message: str) -> None:
    """Print a warning line. Suppressed when --quiet."""
    if not get_quiet():
        _print(f"   ! {message}")


def warn_always(message: str) -> None:
    """Print a warning line even when --quiet. Use sparingly for critical info."""
    _print(f"   ! {message}")


def final(message: str) -> None:
    """
    Print the final result line. Always shown (even in --quiet) because
    callers need to confirm whether the install succeeded.
    """
    _print(f"\n{message}")
