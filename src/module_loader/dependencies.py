"""
Module dependency checks for the server (startup and module management API).

The graph logic lives in :mod:`src.module_graph`; this file supplies the set
of modules that are actually available in the current mode:

- dev mode: modules in ``PLUGINS_DIR``
- production: ``.chacc`` archives in ``MODULES_INSTALLED_DIR`` (minus the
  ones disabled in the database, when a session is given)
"""

from __future__ import annotations

import logging

from src.constants import DEVELOPMENT_MODE, MODULES_INSTALLED_DIR, PLUGINS_DIR
from src.module_graph import (
    DependencyDeclarationError,
    GraphReport,
    archive_metas,
    check_graph,
    declared_dependencies,
    scan_module_directory,
)

BANNER = "=" * 65


def available_module_metas(db=None, dev: bool | None = None) -> dict[str, dict]:
    """Modules the server would load in the current mode: name -> module_meta."""
    dev = DEVELOPMENT_MODE if dev is None else dev
    if dev:
        return {name: info["meta"] for name, info in scan_module_directory(PLUGINS_DIR).items()}
    metas = archive_metas(MODULES_INSTALLED_DIR)
    if db is not None:
        from src.database import ModuleRecord

        disabled = {
            r.name for r in db.query(ModuleRecord).filter(ModuleRecord.is_enabled.is_(False)).all()
        }
        metas = {name: meta for name, meta in metas.items() if name not in disabled}
    return metas


def graph_payload(db=None, dev: bool | None = None) -> dict:
    """
    The module dependency graph for the current mode, as plain JSON.

    Nodes are the modules the server would load, plus disabled ones (production)
    and declared dependencies that are not installed at all (``state: missing``).
    Node states: ``ok``, ``blocked``, ``disabled``, ``missing``.
    """
    dev = DEVELOPMENT_MODE if dev is None else dev
    if dev:
        all_metas = available_module_metas(dev=True)
        enabled = dict(all_metas)
    else:
        all_metas = archive_metas(MODULES_INSTALLED_DIR)
        enabled = available_module_metas(db, dev=False)

    report = check_graph(enabled)
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    for name, meta in sorted(all_metas.items()):
        try:
            required, optional = declared_dependencies(meta or {})
        except DependencyDeclarationError:
            required, optional = [], []
        if name not in enabled:
            state, reason = "disabled", "Disabled in the database."
        elif name in report.blocked:
            state, reason = "blocked", report.blocked[name]
        else:
            state, reason = "ok", None
        nodes[name] = {
            "name": name,
            "display_name": (meta or {}).get("display_name") or name,
            "version": (meta or {}).get("version"),
            "state": state,
            "reason": reason,
            "required": required,
            "optional": optional,
            "missing_optional": report.missing_optional.get(name, []),
        }
        for kind, targets in (("required", required), ("optional", optional)):
            for target in targets:
                edges.append(
                    {"from": name, "to": target, "kind": kind, "satisfied": target in enabled}
                )

    for edge in edges:
        if edge["to"] not in nodes:
            nodes[edge["to"]] = {
                "name": edge["to"],
                "display_name": edge["to"],
                "version": None,
                "state": "missing",
                "reason": "Not installed.",
                "required": [],
                "optional": [],
                "missing_optional": [],
            }

    return {
        "mode": "development" if dev else "production",
        "source": PLUGINS_DIR if dev else MODULES_INSTALLED_DIR,
        "load_order": report.order,
        "nodes": list(nodes.values()),
        "edges": edges,
        "how_to_fix": where_to_install(dev),
    }


def where_to_install(dev: bool | None = None) -> str:
    dev = DEVELOPMENT_MODE if dev is None else dev
    if dev:
        return f"add the missing modules to the plugins directory ({PLUGINS_DIR})"
    return "install the missing modules with 'chacc deploy <module>.chacc'"


def log_report(report: GraphReport, logger: logging.Logger, dev: bool | None = None) -> None:
    """Highlight dependency problems in the startup log. Silent when all is well."""
    problems = report.problems()
    if not problems:
        return
    log = logger.error if report.blocked else logger.warning
    log(BANNER)
    log("MODULE DEPENDENCIES NEED ATTENTION")
    for line in problems:
        log(f"  {line}")
    log(f"  To fix: {where_to_install(dev)}, then restart the server.")
    log(BANNER)
