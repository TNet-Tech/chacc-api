"""
Modules as the web console shows them.

In production that is the installed archives (rows in the modules table). In
development it is the folders in plugins/, the modules the development server
actually loads, found the same way as for the dependency graph. Both become a
ModuleView, so the module list and the details read them the same way.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from src.constants import DEVELOPMENT_MODE, MODULES_LOADED_DIR, PLUGINS_DIR
from src.database import ModuleRecord
from src.module_graph import scan_module_directory

INSTALLED = "installed"  # an uploaded .chacc archive, managed from the console
PLUGIN = "plugins"  # a folder in plugins/ (development); edited on disk


@dataclass(frozen=True)
class ModuleView:
    name: str
    source: str
    meta: dict = field(default_factory=dict)
    is_enabled: bool = True
    display_name: str | None = None
    version: str | None = None
    author: str | None = None
    description: str | None = None
    base_path_prefix: str | None = None
    folder: str | None = None  # the module's code
    installed_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def managed(self) -> bool:
        """Whether the console can enable, disable or uninstall it."""
        return self.source == INSTALLED

    @classmethod
    def from_record(cls, record: ModuleRecord) -> "ModuleView":
        folder = os.path.join(MODULES_LOADED_DIR, record.name)
        return cls(
            name=record.name,
            source=INSTALLED,
            meta=record.meta_data or {},
            is_enabled=record.is_enabled,
            display_name=record.display_name,
            version=record.version,
            author=record.author,
            description=record.description,
            base_path_prefix=record.base_path_prefix,
            folder=folder if os.path.isdir(folder) else None,
            installed_at=record.created_at,
            updated_at=record.updated_at,
        )

    @classmethod
    def from_plugin(cls, name: str, module_path: str, meta: dict) -> "ModuleView":
        """A plugins/ folder. The development server loads every plugin, so it is enabled."""
        return cls(
            name=name,
            source=PLUGIN,
            meta=meta,
            display_name=meta.get("display_name"),
            version=meta.get("version"),
            author=meta.get("author"),
            description=meta.get("description"),
            base_path_prefix=meta.get("base_path_prefix"),
            folder=module_path,
        )


def _plugins() -> dict[str, ModuleView]:
    return {
        name: ModuleView.from_plugin(name, info["module_path"], info["meta"] or {})
        for name, info in scan_module_directory(PLUGINS_DIR).items()
    }


def console_modules(db: Session) -> list[ModuleView]:
    """The modules this server loads: plugins/ in development, installed archives otherwise."""
    if DEVELOPMENT_MODE:
        return list(_plugins().values())
    return [ModuleView.from_record(record) for record in db.query(ModuleRecord).all()]


def find_module(db: Session, name: str) -> ModuleView | None:
    """One module by name. In development a plugin wins over an installed archive."""
    if DEVELOPMENT_MODE:
        plugin = _plugins().get(name)
        if plugin:
            return plugin
    record = db.query(ModuleRecord).filter(ModuleRecord.name == name).first()
    return ModuleView.from_record(record) if record else None
