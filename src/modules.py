"""
ChaCC API Module Management Routes.

This module contains the FastAPI routes for managing ChaCC modules:
- install_chacc_module_endpoint: Install a new module from .chacc package
- get_modules_endpoint: Get list of all installed modules
- enable_module_endpoint: Enable a module
- disable_module_endpoint: Disable a module
- uninstall_module_endpoint: Uninstall a module

The actual module loading logic is in src/module_loader.py.
"""

import json
import os
import shutil
import tempfile
import zipfile

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from chacc_cli.commands import validate_module_name
from src.chacc_dependency_manager import (
    invalidate_module_cache,
)
from src.chacc_dependency_manager import (
    resolve_chacc_dependencies as re_resolve_dependencies,
)
from src.constants import (
    BASE_DIR,
    MAX_MODULE_UNCOMPRESSED_SIZE,
    MAX_MODULE_UPLOAD_SIZE,
    MODULE_UPLOAD_CHUNK_SIZE,
    MODULES_INSTALLED_DIR,
    MODULES_LOADED_DIR,
    MODULES_UPLOAD_DIR,
)
from src.database import ModuleRecord, get_async_db, get_db
from src.logger import configure_logging, get_default_log_level
from src.module_loader.archive import (
    get_chacc_filepath,
    safe_extract,
)

chacc_logger = configure_logging(log_level=get_default_log_level())


modules_router = APIRouter(tags=["Core"])
security = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(security)
) -> object | None:
    """
    Optional authentication dependency.

    If the authentication module is loaded and get_current_user is registered,
    it will require authentication. Otherwise, it returns None (allows access).

    This allows core APIs to be open when authentication is not present,
    but protected when the authentication module is loaded.
    """
    backbone_context = getattr(request.app.state, "backbone_context", None)

    if backbone_context is None:
        chacc_logger.info("NO BACKBONE CONTEXT. ALLOW ACCESS TO CORE ROUTES")
        return None

    get_current_user = backbone_context.get_service("get_current_user")

    if get_current_user is None:
        chacc_logger.info("NO AUTHENTICATION MODULE, ALLOW ACCESS TO CORE ROUTES")
        return None

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        scheme, credentials = auth_header.split(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        credentials_obj = HTTPAuthorizationCredentials(scheme="Bearer", credentials=credentials)
        current_user = await get_current_user(credentials_obj)

        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return current_user
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


class ModuleUploadSizeLimitMiddleware:
    """
    Pure ASGI middleware that rejects oversized module uploads early.

    If a POST to the module install endpoint declares a ``Content-Length``
    larger than the allowed limit, it is rejected with 413 before the body is
    read. Requests without a declared length (chunked) are still guarded by
    the per-file streaming check in the endpoint itself.
    """

    MULTIPART_OVERHEAD = 64 * 1024

    def __init__(self, app, path_prefix: str = "", max_size: int = MAX_MODULE_UPLOAD_SIZE):
        self.app = app
        self.paths = {f"{path_prefix}/modules", f"{path_prefix}/modules/"}
        self.max_size = max_size

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope.get("method") == "POST"
            and scope.get("path") in self.paths
        ):
            content_length = None
            for name, value in scope.get("headers", []):
                if name == b"content-length":
                    try:
                        content_length = int(value)
                    except ValueError:
                        content_length = None
                    break
            if (
                content_length is not None
                and content_length > self.max_size + self.MULTIPART_OVERHEAD
            ):
                response = JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={"detail": _too_large_message(self.max_size)},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _too_large_message(max_size: int) -> str:
    return f"Module package exceeds the maximum allowed size of {max_size / (1024 * 1024):g} MB."


async def _stream_upload_to_disk(file: UploadFile, max_size: int) -> str:
    """
    Stream an uploaded file to a temporary file in chunks, enforcing ``max_size``.

    Returns the path of the temporary file. The caller is responsible for
    removing or moving it.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".chacc.part", dir=MODULES_UPLOAD_DIR)
    total = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(MODULE_UPLOAD_CHUNK_SIZE):
                total += len(chunk)
                if total > max_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=_too_large_message(max_size),
                    )
                out.write(chunk)
    except BaseException:
        _remove_quietly(tmp_path)
        raise
    finally:
        await file.close()

    if total == 0:
        _remove_quietly(tmp_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded module package is empty.",
        )
    return tmp_path


def _remove_quietly(path: str | None) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            chacc_logger.warning(f"Could not remove temporary upload file '{path}'.")


def _read_module_archive(archive_path: str) -> tuple[str, dict[str, str]]:
    """
    Validate a .chacc archive on disk and return (module_name, module_requirements).

    Raises HTTPException for invalid packages.
    """
    try:
        zip_ref = zipfile.ZipFile(archive_path, "r")
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a valid .chacc (zip) package.",
        )

    with zip_ref:
        uncompressed_size = sum(info.file_size for info in zip_ref.infolist())
        if uncompressed_size > MAX_MODULE_UNCOMPRESSED_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    "Module package expands beyond the maximum allowed uncompressed size of "
                    f"{MAX_MODULE_UNCOMPRESSED_SIZE / (1024 * 1024):g} MB."
                ),
            )

        try:
            with zip_ref.open("module_meta.json") as meta_file:
                meta_data = json.load(meta_file)
        except (KeyError, json.JSONDecodeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing or invalid 'module_meta.json' in the .chacc package.",
            )

        module_name = meta_data.get("name")
        if not module_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'name' field is missing in 'module_meta.json'.",
            )

        try:
            module_name = validate_module_name(module_name)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid module name in module_meta.json: {exc}",
            )

        module_requirements = {}
        try:
            with zip_ref.open("requirements.txt") as req_file:
                module_requirements[module_name] = req_file.read().decode("utf-8")
        except KeyError:
            pass

    return module_name, module_requirements


def _extract_module_archive(module_name: str, target_chacc_path: str) -> None:
    loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
    if os.path.exists(loaded_module_dir):
        shutil.rmtree(loaded_module_dir)
    with zipfile.ZipFile(target_chacc_path, "r") as zip_ref:
        os.makedirs(loaded_module_dir, exist_ok=True)
        safe_extract(zip_ref, loaded_module_dir)
        os.utime(
            loaded_module_dir,
            (os.path.getmtime(target_chacc_path), os.path.getmtime(target_chacc_path)),
        )
    # Remove any stale *_chacc_temp directories that may have leaked into the archive
    for item in os.listdir(loaded_module_dir):
        if item.endswith("_chacc_temp"):
            temp_path = os.path.join(loaded_module_dir, item)
            shutil.rmtree(temp_path, ignore_errors=True)
            chacc_logger.info(f"Removed stale {item} directory from {loaded_module_dir}")
    chacc_logger.info(f"Successfully unzipped module '{module_name}' to '{loaded_module_dir}'.")


@modules_router.post("/modules/", dependencies=[])
@modules_router.post("/modules", dependencies=[])
async def install_chacc_module_endpoint(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: object | None = Depends(get_current_user_optional),
):
    """
    Installs a new ChaCC API module from an .chacc package.

    The upload is streamed to disk in chunks (never fully buffered in memory)
    and limited to ``MAX_MODULE_UPLOAD_SIZE`` bytes (default 10 MB).
    Resolves dependencies BEFORE unzipping to prevent inconsistent state.
    Requires server restart to activate/deactivate the new module.
    """
    if not file.filename or not file.filename.endswith(".chacc"):
        chacc_logger.error(f"Uploaded file '{file.filename}' is not a .chacc package.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .chacc module packages are allowed.",
        )

    tmp_path = await _stream_upload_to_disk(file, MAX_MODULE_UPLOAD_SIZE)

    try:
        module_name, module_requirements = await run_in_threadpool(_read_module_archive, tmp_path)

        backbone_req_path = os.path.join(BASE_DIR, "requirements.txt")
        if os.path.exists(backbone_req_path):
            with open(backbone_req_path, "r") as f:
                module_requirements["backbone"] = f.read()

        if module_requirements:
            chacc_logger.info(
                f"Resolving dependencies for module '{module_name}' before installation..."
            )
            from .chacc_dependency_manager import ChaCCDependencyManager

            dm = ChaCCDependencyManager(logger=chacc_logger)
            await dm.dm.resolve_dependencies(module_requirements)
            chacc_logger.info("Dependencies resolved successfully.")

        target_chacc_path = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.chacc")
        # shutil.move is an atomic rename on the same filesystem, copy+delete otherwise.
        await run_in_threadpool(shutil.move, tmp_path, target_chacc_path)
        tmp_path = None
        chacc_logger.info(f"Module archive '{module_name}.chacc' saved to '{target_chacc_path}'.")

        await run_in_threadpool(_extract_module_archive, module_name, target_chacc_path)

        invalidate_module_cache(module_name)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": f"Module '{module_name}' installed/updated successfully. "
                f"Dependencies resolved. Please restart the API server to apply changes."
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        chacc_logger.exception("Error during module installation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Installation failed: {e}"
        )
    finally:
        _remove_quietly(tmp_path)


@modules_router.get("/modules")
async def get_modules_endpoint_no_slash(
    db: Session = Depends(get_db),
    current_user: object | None = Depends(get_current_user_optional),
):
    """Same as GET /modules/ but without trailing slash."""
    return await get_modules_endpoint(db, current_user)


@modules_router.get("/modules/")
async def get_modules_endpoint(
    db: Session = Depends(get_db),
    current_user: object | None = Depends(get_current_user_optional),
):
    """
    Retrieves a list of all installed modules and their current status from the database.
    """
    module_records = db.query(ModuleRecord).all()
    return {
        "modules": [
            {
                "name": record.name,
                "display_name": record.display_name,
                "version": record.version,
                "author": record.author,
                "description": record.description,
                "is_enabled": record.is_enabled,
                "base_path_prefix": record.base_path_prefix,
            }
            for record in module_records
        ]
    }


@modules_router.post("/modules/{module_name}/enable")
async def enable_module_endpoint(
    module_name: str,
    db: Session = Depends(get_db),
    current_user: object | None = Depends(get_current_user_optional),
):
    """
    Marks a module as enabled in the database.
    Resolves dependencies BEFORE unzipping to prevent inconsistent state.
    Requires server restart to take effect.
    """
    module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
    if not module_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Module not found in database."
        )

    if module_record.is_enabled:
        return JSONResponse(content={"message": f"Module '{module_name}' is already enabled."})

    chacc_filepath = get_chacc_filepath(module_name)
    if not chacc_filepath:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Module archive not found."
        )

    actual_module_name = module_name
    try:
        with (
            zipfile.ZipFile(chacc_filepath, "r") as zip_ref,
            zip_ref.open("module_meta.json") as meta_file,
        ):
            meta_data = json.load(meta_file)
            actual_module_name = meta_data.get("name", module_name)
    except (zipfile.BadZipFile, json.JSONDecodeError, OSError) as e:
        chacc_logger.warning(f"Could not read module_meta.json from {chacc_filepath}: {e}")

    module_requirements = {}
    try:
        with zipfile.ZipFile(chacc_filepath, "r") as zip_ref:
            try:
                with zip_ref.open("requirements.txt") as req_file:
                    req_content = req_file.read().decode("utf-8")
                    module_requirements[actual_module_name] = req_content
            except KeyError:
                pass
    except (zipfile.BadZipFile, OSError) as e:
        chacc_logger.error(f"Could not read requirements from {module_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not read module requirements: {e}",
        )

    backbone_req_path = os.path.join(BASE_DIR, "requirements.txt")
    if os.path.exists(backbone_req_path):
        with open(backbone_req_path, "r") as f:
            module_requirements["backbone"] = f.read()

    if module_requirements:
        chacc_logger.info(
            f"Resolving dependencies for module '{actual_module_name}' before enabling..."
        )
        try:
            from .chacc_dependency_manager import ChaCCDependencyManager

            dm = ChaCCDependencyManager(logger=chacc_logger)
            await dm.resolve_dependencies()
            chacc_logger.info("Dependencies resolved successfully.")
        except Exception as e:  # noqa: BLE001
            chacc_logger.error(f"Dependency resolution failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Dependency resolution failed: {e}",
            )

    loaded_module_dir = os.path.join(MODULES_LOADED_DIR, actual_module_name)
    shutil.rmtree(loaded_module_dir, ignore_errors=True)
    with zipfile.ZipFile(chacc_filepath, "r") as zip_ref:
        os.makedirs(loaded_module_dir, exist_ok=True)
        safe_extract(zip_ref, loaded_module_dir)
        os.utime(
            loaded_module_dir, (os.path.getmtime(chacc_filepath), os.path.getmtime(chacc_filepath))
        )
    # Remove any stale *_chacc_temp directories that may have leaked into the archive
    for item in os.listdir(loaded_module_dir):
        if item.endswith("_chacc_temp"):
            temp_path = os.path.join(loaded_module_dir, item)
            shutil.rmtree(temp_path, ignore_errors=True)
            chacc_logger.info(f"Removed stale {item} directory from {loaded_module_dir}")

    module_record.is_enabled = True
    db.commit()
    db.refresh(module_record)
    chacc_logger.info(
        f"Module '{actual_module_name}' marked as enabled in DB. Please restart the API server to activate."
    )

    invalidate_module_cache(module_name)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": f"Module '{actual_module_name}' enabled. "
            f"Dependencies resolved. Please restart the server for changes to take effect."
        },
    )


@modules_router.post("/modules/{module_name}/disable")
async def disable_module_endpoint(
    module_name: str,
    db: Session = Depends(get_db),
    current_user: object | None = Depends(get_current_user_optional),
):
    """
    Marks a module as disabled in the database. Requires server restart to take effect.
    """
    module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
    if not module_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Module not found in database."
        )

    if not module_record.is_enabled:
        return JSONResponse(content={"message": f"Module '{module_name}' is already disabled."})

    actual_module_name = module_record.name
    loaded_module_dir = os.path.join(MODULES_LOADED_DIR, actual_module_name)
    if os.path.exists(loaded_module_dir):
        shutil.rmtree(loaded_module_dir)
        chacc_logger.info(f"Successfully deleted module code directory: {loaded_module_dir}")

    module_record.is_enabled = False
    db.commit()
    db.refresh(module_record)
    chacc_logger.info(
        f"Module '{actual_module_name}' marked as disabled in DB. Please restart the API server to deactivate."
    )

    invalidate_module_cache(module_name)
    await re_resolve_dependencies()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": f"Module '{actual_module_name}' disabled. Please restart the server for changes to take effect."
        },
    )


@modules_router.delete("/modules/{module_name}/uninstall")
async def uninstall_module_endpoint(
    module_name: str,
    db: Session = Depends(get_db),
    current_user: object | None = Depends(get_current_user_optional),
):
    """
    Uninstalls a module by removing its code from disk and its record from the database.
    Requires server restart to take full effect.
    """

    module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
    if not module_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Module not found in database."
        )

    actual_module_name = module_record.name

    try:
        loaded_module_dir = os.path.join(MODULES_LOADED_DIR, actual_module_name)
        if os.path.exists(loaded_module_dir):
            shutil.rmtree(loaded_module_dir)
            chacc_logger.info(f"Successfully deleted module code directory: {loaded_module_dir}")

        archive_file_path = get_chacc_filepath(module_name)

        if archive_file_path and os.path.exists(archive_file_path):
            os.remove(archive_file_path)
            chacc_logger.info(f"Successfully deleted module archive: {archive_file_path}")

        db.delete(module_record)
        db.commit()
        chacc_logger.info(f"Module '{actual_module_name}' record deleted from database.")

        invalidate_module_cache(module_name)
        await re_resolve_dependencies()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": f"Module '{actual_module_name}' uninstalled. Please restart the API server to apply changes."
            },
        )

    except Exception as e:
        db.rollback()
        chacc_logger.exception(f"Error during module uninstall of '{module_name}'.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to uninstall module: {e}. Manual intervention may be required.",
        )
