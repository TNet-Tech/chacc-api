"""Module loader package for ChaCC API.

This package provides modular loading, discovery, and management of ChaCC modules.
"""

from .loader import load_modules, load_single_module
from .discovery import discover_and_import_models
from .archive import (
    get_chacc_filepath,
    extract_module_names_from_chacc_files,
    collect_module_requirements,
    process_module_archives,
    unzip_modules,
)
from .metadata import sync_database_with_filesystem
from .testing import run_module_tests

__all__ = [
    "load_modules",
    "load_single_module",
    "discover_and_import_models",
    "get_chacc_filepath",
    "extract_module_names_from_chacc_files",
    "collect_module_requirements",
    "process_module_archives",
    "unzip_modules",
    "sync_database_with_filesystem",
    "run_module_tests",
]