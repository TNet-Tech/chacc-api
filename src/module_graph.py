"""
Module dependency graph.

A module declares the other ChaCC modules it needs in ``module_meta.json``::

    "module_dependencies": {
        "required": ["chacc_authentication"],
        "optional": ["chacc_file_manager"]
    }

- **required**: the module cannot work without these. It is refused at
  install/enable time and is not loaded at startup while one is missing.
- **optional**: the module works without these, with fewer features. A missing
  optional module is only reported.

Nothing is installed automatically: missing modules are reported and the user
installs them. "Available" means the modules the server loads in the current
mode (``plugins/`` in dev mode, installed archives in production).

This file has no FastAPI or database imports so the CLI can use it too.
"""

from __future__ import annotations

import graphlib
import json
import os
import re
import zipfile
from dataclasses import dataclass, field

DEPENDENCIES_KEY = "module_dependencies"
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DependencyDeclarationError(ValueError):
    """``module_dependencies`` in module_meta.json is malformed."""


def declared_dependencies(meta: dict) -> tuple[list[str], list[str]]:
    """
    Return ``(required, optional)`` module names declared in ``meta``.

    A module without ``module_dependencies`` has no dependencies. Raises
    DependencyDeclarationError if the block is malformed.
    """
    block = meta.get(DEPENDENCIES_KEY)
    if block is None:
        return [], []
    if not isinstance(block, dict):
        raise DependencyDeclarationError(
            f"'{DEPENDENCIES_KEY}' must be an object with 'required' and/or 'optional' lists."
        )
    unknown = set(block) - {"required", "optional"}
    if unknown:
        raise DependencyDeclarationError(
            f"Unknown key(s) in '{DEPENDENCIES_KEY}': {', '.join(sorted(unknown))}. "
            "Use 'required' and 'optional'."
        )

    lists = {}
    for kind in ("required", "optional"):
        names = block.get(kind, [])
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise DependencyDeclarationError(
                f"'{DEPENDENCIES_KEY}.{kind}' must be a list of module names."
            )
        names = [n.strip() for n in names]
        for name in names:
            if not _NAME_RE.match(name):
                raise DependencyDeclarationError(
                    f"Invalid module name '{name}' in '{DEPENDENCIES_KEY}.{kind}'."
                )
        lists[kind] = list(dict.fromkeys(names))  # dedupe, keep order

    own_name = meta.get("name")
    if own_name and own_name in lists["required"] + lists["optional"]:
        raise DependencyDeclarationError(f"Module '{own_name}' cannot depend on itself.")
    both = set(lists["required"]) & set(lists["optional"])
    if both:
        raise DependencyDeclarationError(
            f"Module(s) listed as both required and optional: {', '.join(sorted(both))}."
        )
    return lists["required"], lists["optional"]


@dataclass
class MissingDependencies:
    required: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.required or self.optional)


def missing_dependencies(meta: dict, available: set[str] | list[str]) -> MissingDependencies:
    """Which of ``meta``'s declared dependencies are not in ``available``."""
    required, optional = declared_dependencies(meta)
    available = set(available)
    return MissingDependencies(
        required=[n for n in required if n not in available],
        optional=[n for n in optional if n not in available],
    )


@dataclass
class GraphReport:
    """Result of checking a set of modules against each other."""

    order: list[str]  # loadable modules, dependencies first
    blocked: dict[str, str]  # module -> why it will not be loaded
    missing_optional: dict[str, list[str]]  # module -> optional modules not available
    invalid: dict[str, str]  # module -> declaration error

    def problems(self) -> list[str]:
        """Human-readable lines, one per problem, for highlighting to the user."""
        lines = [f"{name}: NOT LOADED - {why}" for name, why in self.blocked.items()]
        lines += [
            f"{name}: optional module(s) not installed: {', '.join(missing)}"
            for name, missing in self.missing_optional.items()
        ]
        return lines


def check_graph(modules: dict[str, dict]) -> GraphReport:
    """
    Check modules (name -> module_meta dict) against each other.

    A module is blocked when a required module is missing, is itself blocked,
    has an invalid declaration, or is part of a required-dependency cycle.
    Everything else is returned in an order where each module comes after the
    modules it depends on (required and available optional ones).
    """
    deps: dict[str, tuple[list[str], list[str]]] = {}
    blocked: dict[str, str] = {}
    invalid: dict[str, str] = {}
    for name, meta in modules.items():
        try:
            deps[name] = declared_dependencies(meta or {})
        except DependencyDeclarationError as exc:
            invalid[name] = str(exc)
            blocked[name] = f"invalid '{DEPENDENCIES_KEY}': {exc}"

    for name, (required, _optional) in deps.items():
        missing = [r for r in required if r not in modules]
        if missing:
            blocked[name] = f"missing required module(s): {', '.join(missing)}"

    # Required-dependency cycles: nothing in a cycle can be set up first.
    graph = {n: {r for r in deps[n][0] if r in deps} for n in deps if n not in blocked}
    while True:
        try:
            tuple(graphlib.TopologicalSorter(graph).static_order())
            break
        except graphlib.CycleError as exc:
            cycle = list(dict.fromkeys(exc.args[1]))
            for name in cycle:
                blocked[name] = f"required dependency cycle: {' -> '.join(exc.args[1])}"
                graph.pop(name, None)
            graph = {n: d - set(cycle) for n, d in graph.items()}

    # Propagate: depending on a blocked module blocks you too.
    changed = True
    while changed:
        changed = False
        for name, (required, _optional) in deps.items():
            if name in blocked:
                continue
            bad = [r for r in required if r in blocked]
            if bad:
                blocked[name] = f"required module(s) not loaded: {', '.join(bad)}"
                changed = True

    loadable = [n for n in modules if n not in blocked]
    missing_optional = {}
    order_graph: dict[str, set[str]] = {}
    for name in loadable:
        required, optional = deps[name]
        missing = [o for o in optional if o not in modules or o in blocked]
        if missing:
            missing_optional[name] = missing
        wanted = set(required) | (set(optional) - set(missing))
        order_graph[name] = wanted & set(loadable)

    try:
        order = list(graphlib.TopologicalSorter(order_graph).static_order())
    except graphlib.CycleError:
        # Only optional edges can still form a cycle; their order does not matter.
        order = sorted(loadable)

    return GraphReport(
        order=order, blocked=blocked, missing_optional=missing_optional, invalid=invalid
    )


# ---------- Finding the available modules (filesystem only) ----------


def read_archive_meta(path: str) -> dict | None:
    """module_meta.json from a .chacc archive, or None if unreadable."""
    try:
        with zipfile.ZipFile(path) as zf, zf.open("module_meta.json") as f:
            meta = json.load(f)
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None
    return meta if isinstance(meta, dict) else None


def archive_metas(directory: str) -> dict[str, dict]:
    """name -> module_meta for every .chacc archive in ``directory``."""
    metas: dict[str, dict] = {}
    if not os.path.isdir(directory):
        return metas
    for filename in sorted(os.listdir(directory)):
        if filename.endswith(".chacc"):
            meta = read_archive_meta(os.path.join(directory, filename))
            if meta is not None:
                metas[meta.get("name") or filename.removesuffix(".chacc")] = meta
    return metas


def scan_module_directory(directory: str) -> dict[str, dict]:
    """
    Find module folders in ``directory`` (e.g. plugins/).

    A module is a folder with module_meta.json, either directly or one level
    down (a repo checkout containing the module). Returns
    name -> {"name", "module_path", "meta"}.
    """
    modules: dict[str, dict] = {}
    if not os.path.isdir(directory):
        return modules
    for entry in sorted(os.listdir(directory)):
        module_path = os.path.join(directory, entry)
        if not os.path.isdir(module_path) or entry.startswith("."):
            continue
        meta_path = os.path.join(module_path, "module_meta.json")
        if not os.path.exists(meta_path):
            for sub in sorted(os.listdir(module_path)):
                candidate = os.path.join(module_path, sub, "module_meta.json")
                if not sub.startswith(".") and os.path.isfile(candidate):
                    module_path, meta_path = os.path.join(module_path, sub), candidate
                    break
        if not os.path.exists(meta_path):
            continue
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict):
            continue
        name = meta.get("name", entry)
        modules[name] = {"name": name, "module_path": module_path, "meta": meta}
    return modules


def dependents_of(name: str, modules: dict[str, dict]) -> list[str]:
    """Modules that list ``name`` as a required dependency."""
    result = []
    for other, meta in modules.items():
        try:
            required, _ = declared_dependencies(meta or {})
        except DependencyDeclarationError:
            continue
        if name in required:
            result.append(other)
    return sorted(result)
