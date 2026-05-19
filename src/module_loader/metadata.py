"""Metadata management for ChaCC API modules.

Synchronises database records with the filesystem state, removing
records for modules that are no longer present on disk.
"""

import os
import shutil
from typing import Dict

from src.constants import MODULES_LOADED_DIR

chacc_logger = __import__("src.logger", fromlist=["configure_logging"]).configure_logging(log_level=__import__("src.logger", fromlist=["LogLevels"]).LogLevels.INFO)


def sync_database_with_filesystem(
    chacc_to_module_name: Dict[str, str], existing_records: Dict, db
):
    """Remove DB records for modules that are no longer on disk.

    Args:
        chacc_to_module_name: Mapping of .chacc filename to module name.
        existing_records: Dict of existing DB records.
        db: Database session.
    """
    installed_module_names = set(chacc_to_module_name.values())

    for module_name, record in list(existing_records.items()):
        if module_name not in installed_module_names:
            db.delete(record)
            chacc_logger.warning(
                f"Module '{module_name}' record found in DB but not on disk. "
                f"Deleting record and its code."
            )
            loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
            if os.path.exists(loaded_module_dir):
                shutil.rmtree(loaded_module_dir)