"""Archive handling for ChaCC API modules.

Manages .chacc archive operations: extracting module names from
module_meta.json, locating archive files, collecting requirements,
determining which archives need reprocessing, and extracting archives.
"""

import json
import os
import shutil
import zipfile

from sqlalchemy.exc import SQLAlchemyError

from src.constants import MODULES_INSTALLED_DIR, MODULES_LOADED_DIR
from src.database import ModuleRecord
from src.logger import configure_logging, get_default_log_level

chacc_logger = configure_logging(log_level=get_default_log_level())


def safe_extract(zip_ref: zipfile.ZipFile, target_dir: str) -> None:
    target_base = os.path.realpath(target_dir)
    for member in zip_ref.namelist():
        member_path = os.path.realpath(os.path.join(target_dir, member))
        if not member_path.startswith(target_base + os.sep) and member_path != target_base:
            raise ValueError(f"Unsafe path in archive: {member}")
    zip_ref.extractall(target_dir)


def get_chacc_filepath(module_name: str, chacc_to_module_name: dict | None = None) -> str | None:
    """Find the .chacc file path for a given module name.

    Args:
        module_name: Name of the module to find.
        chacc_to_module_name: Optional mapping of .chacc filename to module name cache.

    Returns:
        Path to .chacc file if found, None otherwise.
    """
    if chacc_to_module_name is None:
        chacc_to_module_name = extract_module_names_from_chacc_files(
            [f for f in os.listdir(MODULES_INSTALLED_DIR) if f.endswith(".chacc")]
        )

    for chacc_filename, mapped_name in chacc_to_module_name.items():
        if mapped_name == module_name:
            chacc_filepath = os.path.join(MODULES_INSTALLED_DIR, chacc_filename)
            if os.path.exists(chacc_filepath):
                chacc_logger.info(
                    f"Found matching .chacc file for module '{module_name}': {chacc_filename}"
                )
                return chacc_filepath

    return None


def extract_module_names_from_chacc_files(installed_chacc_files: list[str]) -> dict[str, str]:
    """Extract module names from module_meta.json inside .chacc files.

    Args:
        installed_chacc_files: List of .chacc filenames.

    Returns:
        Dict mapping .chacc filename -> module name.
    """
    chacc_to_module_name = {}

    for chacc_filename in installed_chacc_files:
        chacc_filepath = os.path.join(MODULES_INSTALLED_DIR, chacc_filename)
        try:
            with zipfile.ZipFile(chacc_filepath, "r") as zip_ref:
                try:
                    with zip_ref.open("module_meta.json") as meta_file:
                        meta_data = json.load(meta_file)
                        module_name = meta_data.get("name")
                        if module_name:
                            chacc_to_module_name[chacc_filename] = module_name
                        else:
                            chacc_logger.warning(
                                f"module_meta.json in {chacc_filename} missing 'name' field, using filename"
                            )
                            chacc_to_module_name[chacc_filename] = chacc_filename.replace(
                                ".chacc", ""
                            )
                except KeyError:
                    chacc_logger.warning(
                        f"No module_meta.json found in {chacc_filename}, using filename as module name"
                    )
                    chacc_to_module_name[chacc_filename] = chacc_filename.replace(".chacc", "")
        except (zipfile.BadZipFile, json.JSONDecodeError, OSError, KeyError) as e:
            chacc_logger.warning(f"Could not read module_meta from {chacc_filename}: {e}")
            chacc_to_module_name[chacc_filename] = chacc_filename.replace(".chacc", "")

    return chacc_to_module_name


def read_archive_requirements(zip_ref: zipfile.ZipFile, meta: dict | None) -> str | None:
    """
    The module's Python requirements text from an open archive, or None if it has none.

    Uses ``dependencies_file`` from module_meta.json (default ``requirements.txt``).
    Every caller (upload, enable, boot, CLI) reads requirements through this, so the
    text, and therefore the dependency cache's hash of it, is always the same.
    """
    names = [(meta or {}).get("dependencies_file") or "requirements.txt", "requirements.txt"]
    for name in dict.fromkeys(names):
        try:
            with zip_ref.open(name) as req_file:
                content = req_file.read().decode("utf-8")
        except KeyError:
            continue
        return content if content.strip() else None
    return None


def collect_module_requirements(names: set[str] | None = None) -> dict[str, str]:
    """Python requirements of installed modules, read from their .chacc archives.

    Works before archives are extracted and on a first boot with no database
    records. The backbone is not included: it is installed with ChaCC itself.

    Args:
        names: Only these modules (by module name). None means every archive.

    Returns:
        Dict mapping module_name -> requirements text, for modules that have any.
    """
    modules_requirements = {}

    for chacc_filename in sorted(os.listdir(MODULES_INSTALLED_DIR)):
        if not chacc_filename.endswith(".chacc"):
            continue
        chacc_filepath = os.path.join(MODULES_INSTALLED_DIR, chacc_filename)

        try:
            with zipfile.ZipFile(chacc_filepath, "r") as zip_ref:
                meta_data = {}
                try:
                    with zip_ref.open("module_meta.json") as meta_file:
                        meta_data = json.load(meta_file)
                except KeyError:
                    chacc_logger.warning(
                        f"No module_meta.json found in {chacc_filename}, using filename as module name"
                    )
                module_name = meta_data.get("name") or chacc_filename.removesuffix(".chacc")
                if names is not None and module_name not in names:
                    continue

                content = read_archive_requirements(zip_ref, meta_data)
                if content is not None:
                    modules_requirements[module_name] = content
        except (zipfile.BadZipFile, json.JSONDecodeError, OSError) as e:
            chacc_logger.warning(f"Could not read requirements from {chacc_filename}: {e}")

    return modules_requirements


def process_module_archives(
    installed_chacc_files: list[str],
    chacc_to_module_name: dict[str, str],
    existing_records: dict[str, ModuleRecord],
    db,
) -> list[tuple[str, str, float, bool]]:
    """Determine which .chacc files need re-extraction.

    Args:
        installed_chacc_files: List of .chacc filenames.
        chacc_to_module_name: Mapping of .chacc filename to module name.
        existing_records: Dict of existing DB records.
        db: Database session.

    Returns:
        List of tuples: (module_name, chacc_filepath, chacc_mtime, is_new_module).
    """
    modules_to_process = []

    for chacc_filename in installed_chacc_files:
        module_name = chacc_to_module_name.get(chacc_filename, chacc_filename.replace(".chacc", ""))
        chacc_filepath = os.path.join(MODULES_INSTALLED_DIR, chacc_filename)
        loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)

        chacc_mtime = os.path.getmtime(chacc_filepath)
        is_new_module = module_name not in existing_records

        should_unzip = False
        if not os.path.exists(loaded_module_dir):
            chacc_logger.info(f"Module detected on disk: '{module_name}'.")
            should_unzip = True
        else:
            loaded_mtime = os.path.getmtime(loaded_module_dir)
            if chacc_mtime > loaded_mtime:
                chacc_logger.info(
                    f"Module '{module_name}' archive is newer than loaded directory. Unzipping again."
                )
                shutil.rmtree(loaded_module_dir)
                should_unzip = True

        if should_unzip:
            modules_to_process.append((module_name, chacc_filepath, chacc_mtime, is_new_module))

        if is_new_module:
            meta_file_path = (
                os.path.join(loaded_module_dir, "module_meta.json")
                if os.path.exists(loaded_module_dir)
                else None
            )
            if meta_file_path and os.path.exists(meta_file_path):
                try:
                    with open(meta_file_path, "r") as f:
                        meta_data = json.load(f)

                    new_record = ModuleRecord(
                        name=module_name,
                        display_name=meta_data.get("display_name"),
                        version=meta_data.get("version"),
                        author=meta_data.get("author"),
                        description=meta_data.get("description"),
                        is_enabled=True,
                        base_path_prefix=meta_data.get("base_path_prefix", f"/{module_name}"),
                        meta_data=meta_data,
                    )
                    db.add(new_record)
                    chacc_logger.info(f"New module '{module_name}' found. Created new DB record.")
                except (SQLAlchemyError, OSError) as e:
                    chacc_logger.error(
                        f"Failed to create database record for module '{module_name}': {e}"
                    )

    return modules_to_process


def unzip_modules(
    modules_to_process: list[tuple[str, str, float, bool]],
    existing_records: dict[str, ModuleRecord],
    db,
):
    """Extract archives and create or update DB records.

    Args:
        modules_to_process: List of tuples from process_module_archives().
        existing_records: Dict of existing DB records.
        db: Database session.
    """
    for module_name, chacc_filepath, chacc_mtime, is_new_module in modules_to_process:
        loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)

        chacc_logger.info(f"Unzipping module '{module_name}' to '{loaded_module_dir}'...")
        with zipfile.ZipFile(chacc_filepath, "r") as zip_ref:
            os.makedirs(loaded_module_dir, exist_ok=True)
            safe_extract(zip_ref, loaded_module_dir)
            os.utime(loaded_module_dir, (chacc_mtime, chacc_mtime))
        # Remove any stale *_chacc_temp directories that may have leaked into the archive
        for item in os.listdir(loaded_module_dir):
            if item.endswith("_chacc_temp"):
                temp_path = os.path.join(loaded_module_dir, item)
                shutil.rmtree(temp_path, ignore_errors=True)
                chacc_logger.info(f"Removed stale {item} directory from {loaded_module_dir}")
        chacc_logger.info(f"Unzipping for '{module_name}' completed.")

        meta_file_path = os.path.join(loaded_module_dir, "module_meta.json")
        if os.path.exists(meta_file_path):
            with open(meta_file_path, "r") as f:
                meta_data = json.load(f)

            if is_new_module:
                new_record = ModuleRecord(
                    name=module_name,
                    display_name=meta_data.get("display_name"),
                    version=meta_data.get("version"),
                    author=meta_data.get("author"),
                    description=meta_data.get("description"),
                    is_enabled=True,
                    base_path_prefix=meta_data.get("base_path_prefix", f"/{module_name}"),
                    meta_data=meta_data,
                )
                db.add(new_record)
                chacc_logger.info(f"New module '{module_name}' found. Created new DB record.")
            else:
                record = existing_records[module_name]

                current_meta_data = record.meta_data or {}
                meta_data_changed = (
                    record.display_name != meta_data.get("display_name", record.display_name)
                    or record.version != meta_data.get("version", record.version)
                    or record.author != meta_data.get("author", record.author)
                    or record.description != meta_data.get("description", record.description)
                    or record.base_path_prefix
                    != meta_data.get("base_path_prefix", record.base_path_prefix)
                    or current_meta_data != meta_data
                )

                if meta_data_changed:
                    record.display_name = meta_data.get("display_name", record.display_name)
                    record.version = meta_data.get("version", record.version)
                    record.author = meta_data.get("author", record.author)
                    record.description = meta_data.get("description", record.description)
                    record.base_path_prefix = meta_data.get(
                        "base_path_prefix", record.base_path_prefix
                    )
                    record.meta_data = meta_data
                    chacc_logger.info(f"Existing module '{module_name}' metadata updated.")
