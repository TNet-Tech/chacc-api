import logging
import warnings
from collections.abc import Callable
from typing import Any

from decouple import config as decouple_config
from fastapi import FastAPI
from slowapi import Limiter

_warned: set[str] = set()


def _deprecated(old: str, new: str, logger: logging.Logger | None = None) -> None:
    """Warn about a deprecated API; logged once per name so module authors see it."""
    message = f"{old} is deprecated and will be removed in a future release; use {new}."
    warnings.warn(message, DeprecationWarning, stacklevel=3)
    if logger is not None and old not in _warned:
        _warned.add(old)
        logger.warning(message)


class BackboneContext:
    """
    A class to encapsulate common services and context for modules.
    Modules will receive an instance of this class during setup.
    """

    def __init__(
        self,
        app: FastAPI,
        limiter: Limiter,
        logger: logging.Logger,
        db_session_factory,
        async_db_session_factory,
    ):
        self._app = app
        self._limiter = limiter
        self._logger = logger
        self._db_session_factory = db_session_factory
        self._async_db_session_factory = async_db_session_factory
        self._services: dict[str, Callable[..., Any]] = {}

    @property
    def app(self) -> FastAPI:
        """The main FastAPI application instance."""
        return self._app

    @property
    def limiter(self) -> Limiter:
        """
        Deprecated: use ``rate_limit`` (or ``limiter``) from ``chacc_api.rate_limit``.
        Still works in this release.
        """
        _deprecated("context.limiter", "chacc_api.rate_limit", self._logger)
        return self._limiter

    @property
    def logger(self) -> logging.Logger:
        """A centralized logger instance for modules."""
        return self._logger

    @property
    def get_db(self):
        """
        Deprecated: use ``Depends(get_db)`` with ``from chacc_api.database import get_db``.
        Still works in this release.
        """
        _deprecated("context.get_db", "chacc_api.database.get_db", self._logger)
        return self._db_session_factory

    @property
    def get_db_async(self):
        """
        Deprecated: use ``Depends(get_async_db)`` with
        ``from chacc_api.database import get_async_db``. Still works in this release.
        """
        _deprecated("context.get_db_async", "chacc_api.database.get_async_db", self._logger)
        return self._async_db_session_factory

    def register_service(self, name: str, service: Callable[..., Any]):
        """
        Allows a module to register a named service (function or class) to be used by other modules.
        """
        if name in self._services:
            self._logger.warning(f"Service '{name}' is being overridden by a new registration.")
        self._logger.info(f"Service '{name}' has been registered.")
        self._services[name] = service

    def has_service(self, name: str) -> bool:
        """Whether a service with this name is registered (no warning if not)."""
        return name in self._services

    def get_service(self, name: str) -> Callable[..., Any] | None:
        """
        Retrieves a registered service by its name.
        """
        service = self._services.get(name)
        if not service:
            self._logger.warning(f"Service '{name}' not found. Returning None.")
        return service

    def get_module_config(
        self, key: str, module_name: str, default: str | None = None
    ) -> str | None:
        """
        Get a module-specific configuration value from environment variables.

        This method automatically prefixes the key with the module name to avoid
        conflicts between modules. For example, if module_name is 'auth' and
        key is 'API_KEY', it will look for 'AUTH_API_KEY' in environment variables.

        If the prefixed key is not found, it falls back to checking the non-prefixed
        key (e.g., just 'SECRET_KEY') to support global configuration values.

        Args:
            key: The configuration key (e.g., 'API_KEY', 'SECRET')
            module_name: The name of the module (e.g., 'auth', 'jonas')
            default: Default value if the environment variable is not set

        Returns:
            The configuration value or default

        Example:
            # In a module with name 'auth'
            context.get_module_config("API_KEY", "auth")  # Looks for AUTH_API_KEY, then API_KEY
            context.get_module_config("SECRET", "mymodule")  # Looks for MYMODULE_SECRET, then SECRET
        """
        prefixed_key = f"{module_name.upper()}_{key.upper()}"
        value = decouple_config(prefixed_key, default=None)

        if value is None:
            value = decouple_config(key.upper(), default=None)
            if value is not None:
                self._logger.debug(
                    f"Loaded global config '{key.upper()}' for module '{module_name}'"
                )
                prefixed_key = key.upper()

        if value is None and default is not None:
            if isinstance(default, str) and len(default) > 0 or default is not None:
                value = default
                self._logger.debug(f"Config '{prefixed_key}' not found, using default: {default}")
        elif value is not None:
            self._logger.debug(f"Loaded config '{prefixed_key}' for module '{module_name}'")

        return value
