"""
Everything the console shows about one module: what it declares, whether it is
running (and why not), its routes, Python packages, archive and README.
"""

import hashlib
import os
from datetime import datetime

from src import module_packages, module_status
from src.constants import API_PREFIX, DEVELOPMENT_MODE, MODULES_LOADED_DIR, PLUGINS_DIR
from src.database import ModuleRecord
from src.module_loader.archive import get_chacc_filepath
from src.module_loader.dependencies import graph_payload

README_LIMIT = 100_000  # characters


def _iso(value) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _module_folder(name: str) -> str | None:
    """The module's code: plugins/ in development, the extracted archive in production."""
    candidates = [os.path.join(PLUGINS_DIR, name)] if DEVELOPMENT_MODE else []
    candidates.append(os.path.join(MODULES_LOADED_DIR, name))
    return next((path for path in candidates if os.path.isdir(path)), None)


def _read_text(path: str, limit: int) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return None


def _readme(folder: str | None) -> str | None:
    if not folder:
        return None
    for entry in sorted(os.listdir(folder)):
        if entry.lower() in ("readme.md", "readme.txt", "readme"):
            return _read_text(os.path.join(folder, entry), README_LIMIT)
    return None


def _packages(folder: str | None, meta: dict) -> list[dict]:
    if not folder:
        return []
    content = _read_text(
        os.path.join(folder, meta.get("dependencies_file") or "requirements.txt"), 200_000
    )
    return module_packages.requirement_report(content) if content else []


def _archive(name: str) -> dict | None:
    path = get_chacc_filepath(name)
    if not path or not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    stat = os.stat(path)
    return {
        "file": os.path.basename(path),
        "size": stat.st_size,
        "sha256": digest.hexdigest(),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
    }


_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _routes(app, api_path: str) -> list[dict]:
    """
    The module's routes, from the OpenAPI schema: modules often include other
    routers, which newer FastAPI versions keep nested, so walking the router's
    own route list misses them.
    """
    try:
        paths = app.openapi().get("paths", {})
    except Exception:  # noqa: BLE001 - a broken schema must not break the details
        return []
    routes = []
    for path, operations in sorted(paths.items()):
        if path == api_path or path.startswith(api_path + "/"):
            methods = sorted(m.upper() for m in operations if m in _HTTP_METHODS)
            if methods:
                routes.append({"methods": methods, "path": path})
    return routes


def _used_by(name: str, graph: dict) -> dict:
    used = {"required": [], "optional": []}
    for edge in graph["edges"]:
        if edge["to"] == name:
            used[edge["kind"]].append(edge["from"])
    return {kind: sorted(names) for kind, names in used.items()}


def _state(record: ModuleRecord, node: dict | None, route_count: int) -> dict:
    """What is going on with the module right now, in plain words."""
    loaded = module_status.loaded(record.name)
    failure = module_status.failure(record.name)

    if loaded:
        if not record.is_enabled:
            return {
                "code": "stopping",
                "message": "Disabled. It keeps running until the server restarts.",
            }
        return {
            "code": "loaded",
            "message": f"Running. Serves {route_count} route{'s' if route_count != 1 else ''} "
            f"under {loaded['api_path']}.",
            "since": loaded["loaded_at"],
        }
    if failure and not record.is_enabled:
        return {
            "code": "failed",
            "message": "Turned off because it failed to load. Fix the problem, then enable it again.",
            "reason": failure["reason"],
            "since": failure["at"],
        }
    if not record.is_enabled:
        return {"code": "disabled", "message": "Disabled."}
    if node and node["state"] == "blocked":
        return {"code": "blocked", "message": "Can't load.", "reason": node["reason"]}
    if failure:
        return {
            "code": "failed",
            "message": "Failed to load.",
            "reason": failure["reason"],
            "since": failure["at"],
        }
    if DEVELOPMENT_MODE and node is None:
        return {
            "code": "disabled",
            "message": "Not in plugins/, so the development server doesn't load it.",
        }
    return {"code": "pending", "message": "Enabled. Restart the server to load it."}


def module_details(record: ModuleRecord, db, app) -> dict:
    meta = record.meta_data or {}
    graph = graph_payload(db)
    node = next((n for n in graph["nodes"] if n["name"] == record.name), None)
    folder = _module_folder(record.name)
    loaded = module_status.loaded(record.name)
    prefix = record.base_path_prefix or meta.get("base_path_prefix") or f"/{record.name}"
    api_path = loaded["api_path"] if loaded else f"{API_PREFIX}/{prefix.strip('/')}"
    routes = _routes(app, api_path) if loaded else []
    tags = meta.get("tags") or []

    return {
        "name": record.name,
        "display_name": record.display_name or record.name,
        "version": record.version,
        "author": record.author,
        "description": record.description,
        "is_enabled": record.is_enabled,
        "license": meta.get("license"),
        "homepage": meta.get("homepage"),
        "repository": meta.get("repository"),
        "support": meta.get("support"),
        "tags": tags if isinstance(tags, list) else [tags],
        "required_chacc_version": meta.get("required_chacc_version"),
        "api_path": api_path,
        "installed_at": _iso(record.created_at),
        "updated_at": _iso(record.updated_at),
        "dependencies": {
            "required": (node or {}).get("required", []),
            "optional": (node or {}).get("optional", []),
        },
        "used_by": _used_by(record.name, graph),
        "state": _state(record, node, len(routes)),
        "routes": routes,
        "packages": _packages(folder, meta),
        "archive": None if DEVELOPMENT_MODE else _archive(record.name),
        "readme": _readme(folder),
    }
