"""Model discovery for ChaCC API modules.

This module handles dynamic imports of all .py files within a module
directory so that @register_model-decorated classes are automatically
registered in the global model registry used by the migration system.
"""

import os
import importlib.util
import importlib.machinery
import sys
import logging

chacc_logger = __import__("src.logger", fromlist=["configure_logging"]).configure_logging(log_level=__import__("src.logger", fromlist=["LogLevels"]).LogLevels.INFO)


def _register_package(fq_name: str, abs_dir: str, logger: logging.Logger) -> None:
    """Register or update a single namespace package in sys.modules."""
    child_dirs = [
        os.path.abspath(os.path.join(abs_dir, d))
        for d in sorted(os.listdir(abs_dir))
        if os.path.isdir(os.path.join(abs_dir, d)) and not d.startswith(".") and d != "__pycache__"
    ]

    if fq_name in sys.modules:
        existing = sys.modules[fq_name]
        search_locs = child_dirs or [abs_dir]
        if not hasattr(existing, "__path__") or list(existing.__path__) != search_locs:
            existing.__path__ = search_locs
        return

    search_locs = child_dirs or [abs_dir]
    pkg_spec = importlib.machinery.ModuleSpec(fq_name, loader=None)
    pkg_spec.submodule_search_locations = search_locs

    pkg = importlib.util.module_from_spec(pkg_spec)
    pkg.__path__ = search_locs
    pkg.__package__ = fq_name
    pkg.__name__ = fq_name
    sys.modules[fq_name] = pkg


def _register_intermediate_packages(prefix: str, relative_dir: str, module_directory_path: str, logger: logging.Logger) -> str:
    """Walk down every ancestral package level and register each in sys.modules."""
    dir_segments = [] if relative_dir in ("", ".") else relative_dir.split(".")
    accumulated = prefix

    for i, part in enumerate(dir_segments):
        fq_name = f"{accumulated}.{part}"
        abs_dir = os.path.abspath(os.path.join(module_directory_path, *dir_segments[: i + 1]))
        _register_package(fq_name, abs_dir, logger)
        accumulated = fq_name

    return accumulated


def discover_and_import_models(module_directory_path: str, module_import_prefix: str, logger: logging.Logger):
    """
    Recursively scans a directory for Python files and imports them.

    Enables automatic model discovery by importing all .py files within a module
    directory. Classes decorated with @register_model are automatically registered
    in the global _model_registry for database migration purposes.

    Args:
        module_directory_path: Path to the module directory to scan.
        module_import_prefix: Python module prefix for constructing import names.
        logger: Logger instance for recording discovery progress and errors.

    Raises:
        ImportError: Handled internally - logs warning and continues.
        Exception: Handled internally - logs error and continues.
    """
    module_directory_path = os.path.abspath(module_directory_path)

    # Build list of all files to import, categorized by type
    init_files = []  # __init__.py files - must be imported first
    other_files = []  # Regular .py files

    for root, dirs, files in os.walk(module_directory_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for file in files:
            if not file.endswith(".py"):
                continue
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, module_directory_path)
            if file == "__init__.py":
                init_files.append((root, file, file_path, rel_path))
            else:
                other_files.append((root, file, file_path, rel_path))

    # First, register ALL directories as packages (namespace packages) so relative imports work
    for root, dirs, files in os.walk(module_directory_path):
        rel_root = os.path.relpath(root, module_directory_path)
        if rel_root == ".":
            rel_root = ""
        package_name = f"{module_import_prefix}.{rel_root.replace(os.sep, '.')}" if rel_root else module_import_prefix
        _register_package(package_name, root, logger)

    # Import __init__.py files first to initialize packages properly
    for root, file, file_path, rel_path in init_files:
        rel_dir = os.path.dirname(rel_path)
        if file == "__init__.py":
            file_stem = ""
            module_dotted = f"{module_import_prefix}.{rel_dir.replace(os.sep, '.')}" if rel_dir else module_import_prefix
        else:
            file_stem = file[:-3]
            dotted_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, ".")
            module_dotted = f"{module_import_prefix}.{dotted_dir}.{file_stem}" if dotted_dir else f"{module_import_prefix}.{file_stem}"

        if module_dotted not in sys.modules:
            try:
                spec = importlib.util.spec_from_file_location(module_dotted, file_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    mod.__package__ = module_dotted
                    mod.__name__ = module_dotted
                    sys.modules[module_dotted] = mod
                    spec.loader.exec_module(mod)
                    logger.debug(f"Imported package init: {module_dotted}")
            except Exception as e:
                logger.warning(f"Failed to import {file_path}: {e}")

    # Then import all other Python files
    for root, file, file_path, rel_path in other_files:
        rel_dir = os.path.dirname(rel_path)
        file_stem = file[:-3]
        dotted_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, ".")
        module_dotted = f"{module_import_prefix}.{dotted_dir}.{file_stem}" if dotted_dir else f"{module_import_prefix}.{file_stem}"

        if module_dotted in sys.modules:
            logger.debug(f"Skipping already imported: {module_dotted}")
            continue

        try:
            # Determine enclosing package for proper relative import support
            parent_dotted = rel_dir.replace(os.sep, ".") if rel_dir else ""
            if parent_dotted:
                enclosing_package = _register_intermediate_packages(
                    prefix=module_import_prefix,
                    relative_dir=parent_dotted,
                    module_directory_path=module_directory_path,
                    logger=logger,
                )
            else:
                enclosing_package = module_import_prefix

            spec = importlib.util.spec_from_file_location(module_dotted, file_path)
            if not spec or not spec.loader:
                logger.warning(f"Could not create spec for {file_path}")
                continue

            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = enclosing_package
            mod.__name__ = module_dotted
            sys.modules[module_dotted] = mod
            spec.loader.exec_module(mod)
            logger.info(f"Scanned for models from: {module_dotted}")

        except ImportError as e:
            if "already defined for this MetaData instance" in str(e):
                logger.warning(f"Skipping {file_path}: its table is already registered in metadata.")
                continue
            logger.warning(f"Relative import issue in {file_path}: {e}")
        except SyntaxError as e:
            logger.warning(f"SyntaxError in {file_path} (line {e.lineno}): {e.msg}")
        except Exception as e:
            if "already defined for this MetaData instance" in str(e):
                logger.warning(f"Skipping {file_path}: its table is already registered in metadata.")
                continue
            logger.error(f"Failed to import models from {file_path}: {e}", exc_info=True)