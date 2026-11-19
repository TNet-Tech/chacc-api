"""
Who may use the web console and the core module and system routes.

With the authentication module loaded, a user needs the console privilege
(``CHACC_ADMIN_PRIVILEGE``, default ``MANAGE_WEB_CONSOLE``) or ``ALL``.
ChaCC registers the console privilege itself through the module's
``privilege_service`` the first time the console is opened or a protected core
route is called, once per server run.

The privilege's name is never sent to clients: a refused request gets a plain
403 without it.

Without the authentication module, the web console key (``CHACC_CONSOLE_KEY``)
protects the same routes: clients send it in the ``X-ChaCC-Key`` header, as
typed or URL-encoded. The
authentication module always wins: while it is loaded the key isn't accepted.
With neither, the routes stay open; their responses carry an
``X-ChaCC-Warning`` header and the server logs a warning.
"""

import hmac
import re
from urllib.parse import unquote

from fastapi import HTTPException, Request, Response, status

from src.constants import ADMIN_PRIVILEGE_SETTING, CONSOLE_KEY
from src.logger import configure_logging, get_default_log_level

chacc_logger = configure_logging(log_level=get_default_log_level())

DEFAULT_ADMIN_PRIVILEGE = "MANAGE_WEB_CONSOLE"
SUPER_PRIVILEGE = "ALL"
ADMIN_PRIVILEGE_DESCRIPTION = "Use the web console: manage modules and restart the server."
ADMIN_PRIVILEGE_SEVERITY = "CRITICAL"
NO_ACCESS_MESSAGE = "You don't have access to manage this server."

_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,99}")


def resolve_admin_privilege(value: str) -> str:
    """
    The configured privilege name, or the default when it is empty or invalid.

    Never "no privilege": a wrong setting must not make access easier.
    """
    name = value.strip()
    if not name:
        return DEFAULT_ADMIN_PRIVILEGE
    if name == SUPER_PRIVILEGE or not _NAME.fullmatch(name):
        chacc_logger.warning(
            f"CHACC_ADMIN_PRIVILEGE must be a name like {DEFAULT_ADMIN_PRIVILEGE} (capital "
            f"letters, digits and _, not ALL). Using {DEFAULT_ADMIN_PRIVILEGE}."
        )
        return DEFAULT_ADMIN_PRIVILEGE
    return name


ADMIN_PRIVILEGE = resolve_admin_privilege(ADMIN_PRIVILEGE_SETTING)

_registered: set[tuple[int, str]] = set()  # (id of the service, privilege) already registered
_warned_no_check = False


def auth_loaded(context) -> bool:
    return bool(context and context.has_service("get_current_user"))


async def ensure_admin_privilege(context) -> bool:
    """
    Register the console privilege with the authentication module, if it is loaded.

    Safe to call on every request: it calls the module once per server run
    (again after a failure). Never raises; returns whether it is registered.
    """
    if not auth_loaded(context) or not context.has_service("privilege_service"):
        return False
    service = context.get_service("privilege_service")
    key = (id(service), ADMIN_PRIVILEGE)
    if key in _registered:
        return True
    try:
        await service.ensure(
            [(ADMIN_PRIVILEGE, ADMIN_PRIVILEGE_DESCRIPTION, ADMIN_PRIVILEGE_SEVERITY)]
        )
    except Exception as e:  # noqa: BLE001 - access checks must not fail because of this
        chacc_logger.warning(f"Could not register the {ADMIN_PRIVILEGE} privilege: {e}")
        return False
    _registered.add(key)
    chacc_logger.info(f"Registered the {ADMIN_PRIVILEGE} privilege for the web console.")
    return True


def privilege_check(context):
    """The authentication module's ``has_privileges`` service, or None for an older module."""
    global _warned_no_check
    if context.has_service("has_privileges"):
        return context.get_service("has_privileges")
    if not _warned_no_check:
        _warned_no_check = True
        chacc_logger.warning(
            "The authentication module has no 'has_privileges' service, so any logged-in "
            "user can use the web console. Update the module to limit it to admins."
        )
    return None


async def require_admin(context, credentials):
    """
    The user for ``credentials`` if they hold the console privilege or ``ALL``.

    Raises 401 when not logged in and 403 without the privilege; the 403 doesn't
    name the privilege. Returns None when the module can't check privileges.
    """
    has_privileges = privilege_check(context)
    if has_privileges is None:
        return None
    await ensure_admin_privilege(context)
    try:
        return await has_privileges(credentials, [ADMIN_PRIVILEGE, SUPER_PRIVILEGE])
    except HTTPException as e:
        if e.status_code == status.HTTP_403_FORBIDDEN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=NO_ACCESS_MESSAGE)
        raise


# --- Web console key (no authentication module) ---

KEY_HEADER = "X-ChaCC-Key"
KEY_CHALLENGE = "ChaCC-Key"  # WWW-Authenticate value of a 401 that asks for the key
WARNING_HEADER = "X-ChaCC-Warning"
UNPROTECTED_MESSAGE = (
    "The web console isn't protected: anyone who can reach this server can manage its "
    "modules. Set CHACC_CONSOLE_KEY or install the authentication module."
)

_warned_unprotected = False


def access_method(context) -> str:
    """How the console is protected: "login", "key" or "none"."""
    if auth_loaded(context):
        return "login"
    return "key" if CONSOLE_KEY else "none"


def _warn_unprotected() -> None:
    global _warned_unprotected
    if not _warned_unprotected:
        _warned_unprotected = True
        chacc_logger.warning(UNPROTECTED_MESSAGE)


def _key_matches(given: str) -> bool:
    """
    The header holds the key as typed, or URL-encoded. The console and
    ``chacc deploy`` encode it so keys with any characters fit in a header.
    """
    expected = CONSOLE_KEY.encode()
    raw = hmac.compare_digest(given.encode("latin-1", "replace"), expected)
    decoded = hmac.compare_digest(unquote(given).encode(), expected)
    return raw or decoded


def require_console_key(request: Request, response: Response) -> None:
    """
    Check the web console key, for when the authentication module isn't loaded.

    Raises 401 (``WWW-Authenticate: ChaCC-Key``) without the right key. With no
    key configured the request passes, flagged with the warning header.
    """
    if not CONSOLE_KEY:
        _warn_unprotected()
        response.headers[WARNING_HEADER] = UNPROTECTED_MESSAGE
        return
    given = request.headers.get(KEY_HEADER, "")
    if given and _key_matches(given):
        return
    if given:
        client = request.client.host if request.client else "unknown"
        chacc_logger.warning(f"Wrong web console key from {client} for {request.url.path}.")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Wrong web console key." if given else "The web console key is required.",
        headers={"WWW-Authenticate": KEY_CHALLENGE},
    )


def log_console_protection(context) -> None:
    """Startup log line saying how the console is protected."""
    method = access_method(context)
    if method == "none":
        _warn_unprotected()
    elif method == "login" and CONSOLE_KEY:
        chacc_logger.info(
            "CHACC_CONSOLE_KEY is set, but the authentication module protects the web "
            "console, so the key isn't used."
        )
    elif method == "key":
        chacc_logger.info("The web console key (CHACC_CONSOLE_KEY) protects the web console.")
