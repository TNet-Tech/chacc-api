"""
Who may use the web console and the core module and system routes.

With the authentication module loaded, a user needs the console privilege
(``CHACC_ADMIN_PRIVILEGE``, default ``MANAGE_WEB_CONSOLE``) or ``ALL``.
ChaCC registers the console privilege itself through the module's
``privilege_service`` the first time the console is opened or a protected core
route is called, once per server run.

The privilege's name is never sent to clients: a refused request gets a plain
403 without it.
"""

import re

from fastapi import HTTPException, status

from src.constants import ADMIN_PRIVILEGE_SETTING
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
