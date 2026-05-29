"""Model discovery for ChaCC API modules.

This module handles dynamic imports of all .py files within a module
directory so that @register_model-decorated classes are automatically
registered in the global model registry used by the migration system.
"""

import os
import importlib.util
import sys
import logging


def _dotted_name(prefix: str, rel_dir: str, file_stem: str) -> str:
    """Build the dotted module name for a file."""
    sd = "" if rel_dir in ("", ".") else rel_dir.replace(os.sep, ".")
    return f"{prefix}.{sd}.{file_stem}" if sd else f"{prefix}.{file_stem}"


def _enclosing(prefix: str, rel_dir: str) -> str:
    """Return the dotted name of the package owning a file in *rel_dir*."""
    parts = [] if rel_dir in ("", ".") else rel_dir.replace(os.sep, ".").split(".")
    return ".".join([prefix] + parts) if parts else prefix


def discover_and_import_models(
    module_directory_path: str, module_import_prefix: str, logger: logging.Logger
):
    """
    Recursively scans a directory for Python files and imports them.

    Enables automatic model discovery by importing all .py files within a module
    directory. Classes decorated with @register_model are automatically registered
    in the global model registry used by the migration system.

    The parent of *module_directory_path* must already be on ``sys.path``
    (``loader.py`` ensures this by adding ``MODULES_LOADED_DIR``).

    Args:
        module_directory_path: Path to the module directory to scan.
        module_import_prefix: Python module prefix for constructing import names.
        logger: Logger instance for recording discovery progress and errors.
    """
    module_directory_path = os.path.abspath(module_directory_path)

    parent_dir = os.path.dirname(module_directory_path)
    _added_parent = parent_dir not in sys.path

    try:
        if _added_parent:
            sys.path.insert(0, parent_dir)

        depth_groups: dict[int, list[tuple[str, str, str]]] = {}

        for root, dirs, files in os.walk(module_directory_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            rel_root = os.path.relpath(root, module_directory_path)
            depth = 1 if rel_root == "." else rel_root.count(os.sep) + 1
            for file in files:
                if not file.endswith(".py"):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, module_directory_path)
                depth_groups.setdefault(depth, []).append((file_path, rel_path, file))

        for depth in sorted(depth_groups):
            regular = [(fp, rp, f) for fp, rp, f in depth_groups[depth] if f != "__init__.py"]
            inits = [(fp, rp, f) for fp, rp, f in depth_groups[depth] if f == "__init__.py"]

            for file_path, rel_path, file in sorted(regular, key=lambda t: t[2]):
                rel_dir = os.path.dirname(rel_path)
                module_dotted = _dotted_name(module_import_prefix, rel_dir, file[:-3])
                enclosing = _enclosing(module_import_prefix, rel_dir)

                if module_dotted in sys.modules:
                    logger.debug(f"Skipping already imported: {module_dotted}")
                    continue

                try:
                    spec = importlib.util.spec_from_file_location(module_dotted, file_path)
                    if not spec or not spec.loader:
                        logger.warning(f"Could not create spec for {file_path}")
                        continue
                    mod = importlib.util.module_from_spec(spec)
                    mod.__package__ = enclosing
                    mod.__name__ = module_dotted
                    sys.modules[module_dotted] = mod
                    spec.loader.exec_module(mod)
                    logger.info(f"Scanned for models in: {module_dotted}")

                except ImportError as e:
                    if "already defined for this MetaData instance" in str(e):
                        logger.warning(
                            f"Skipping {file_path}: its table is already registered in metadata."
                        )
                        continue
                    logger.error(f"Relative import issue in {file_path}: {e}")
                except SyntaxError as e:
                    logger.error(f"SyntaxError in {file_path} (line {e.lineno}): {e.msg}")
                except Exception as e:
                    if "already defined for this MetaData instance" in str(e):
                        logger.warning(
                            f"Skipping {file_path}: its table is already registered in metadata."
                        )
                        continue
                    logger.error(f"Failed to import models from {file_path}: {e}", exc_info=True)

            for file_path, rel_path, _ in sorted(inits, key=lambda t: t[2]):
                rel_dir = os.path.dirname(rel_path)
                pkg_name = _enclosing(module_import_prefix, rel_dir)

                if pkg_name in sys.modules:
                    logger.debug(f"Skipping already imported: {pkg_name}")
                    continue

                try:
                    spec = importlib.util.spec_from_file_location(pkg_name, file_path)
                    if not spec or not spec.loader:
                        logger.warning(f"Could not create spec for {file_path}")
                        continue
                    mod = importlib.util.module_from_spec(spec)
                    mod.__package__ = pkg_name
                    mod.__name__ = pkg_name
                    sys.modules[pkg_name] = mod
                    spec.loader.exec_module(mod)
                    logger.info(f"Scanned for models in: {pkg_name}")

                except ImportError as e:
                    if "already defined for this MetaData instance" in str(e):
                        logger.warning(
                            f"Skipping {file_path}: its table is already registered in metadata."
                        )
                        continue
                    logger.warning(f"Relative import issue in {file_path}: {e}")
                except SyntaxError as e:
                    logger.warning(f"SyntaxError in {file_path} (line {e.lineno}): {e.msg}")
                except Exception as e:
                    if "already defined for this MetaData instance" in str(e):
                        logger.warning(
                            f"Skipping {file_path}: its table is already registered in metadata."
                        )
                        continue
                    logger.error(f"Failed to import models from {file_path}: {e}", exc_info=True)

    finally:
        if _added_parent and parent_dir in sys.path:
            sys.path.remove(parent_dir)
