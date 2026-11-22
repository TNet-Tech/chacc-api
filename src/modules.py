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

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from chacc_cli.commands import validate_module_name
from src import module_packages, module_status
from src.admin_access import require_admin, require_console_key
from src.constants import (
    API_PREFIX,
    DEVELOPMENT_MODE,
    MAX_MODULE_UNCOMPRESSED_SIZE,
    MAX_MODULE_UPLOAD_SIZE,
    MODULE_UPLOAD_CHUNK_SIZE,
    MODULES_INSTALLED_DIR,
    MODULES_LOADED_DIR,
    MODULES_UPLOAD_DIR,
)
from src.database import ModuleRecord, get_async_db, get_db
from src.logger import configure_logging, get_default_log_level
from src.module_graph import (
    DependencyDeclarationError,
    declared_dependencies,
    dependents_of,
    missing_dependencies,
)
from src.module_loader.archive import (
    get_chacc_filepath,
    read_archive_requirements,
    safe_extract,
)
from src.module_loader.dependencies import available_module_metas, graph_payload
from src.module_view import ModuleView, console_modules, find_module

chacc_logger = configure_logging(log_level=get_default_log_level())


modules_router = APIRouter(tags=["Core"])
security = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> object | None:
    """
    Access check for the core module and system routes (the web console's API).

    With the authentication module, the caller must be logged in (401 otherwise)
    and hold the console privilege or ``ALL`` (403 otherwise). Without it, the
    web console key is checked instead, if one is set. See :mod:`src.admin_access`.
    """
    backbone_context = getattr(request.app.state, "backbone_context", None)
    get_current_user = (
        backbone_context.get_service("get_current_user") if backbone_context else None
    )

    if get_current_user is None:
        require_console_key(request, response)
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
        admin = await require_admin(backbone_context, credentials_obj)
        if admin is not None:
            return admin
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


async def get_current_user_in_production(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> object | None:
    """
    Like :func:`get_current_user_optional`, but open in development mode.

    For read-only views (the dependency graph) that developers should see
    without logging in. In production a login is required when the
    authentication module is loaded.
    """
    if DEVELOPMENT_MODE:
        return None
    return await get_current_user_optional(request, response, credentials)


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


def _read_module_archive(archive_path: str) -> tuple[str, dict[str, str], dict]:
    """
    Validate a .chacc archive on disk and return (module_name, module_requirements, meta).

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

        try:
            declared_dependencies({**meta_data, "name": module_name})
        except DependencyDeclarationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid module_meta.json: {exc}",
            )

        module_requirements = {}
        content = read_archive_requirements(zip_ref, meta_data)
        if content is not None:
            module_requirements[module_name] = content

    return module_name, module_requirements, meta_data


async def _install_module_packages(
    module_name: str, requirements: dict[str, str], is_new: bool
) -> list[str]:
    """
    Resolve and install a module's Python packages. Returns warnings.

    Nothing is installed when resolution fails. Raises HTTPException:
    409 for a conflict, 422 when the requirements can't be resolved, 503 when the
    package index can't be reached.
    """
    from chacc import ResolutionError

    if not requirements:
        # The module has no requirements (any more): unregister it, no network needed.
        await run_in_threadpool(module_packages.forget_module, module_name, chacc_logger)
        return []

    chacc_logger.info(f"Resolving Python packages for module '{module_name}'...")
    try:
        result = await module_packages.resolve_and_install(requirements, chacc_logger)
    except (ResolutionError, module_packages.PackageInstallError) as exc:
        if is_new:
            await run_in_threadpool(module_packages.forget_module, module_name, chacc_logger)
        raise _package_error(module_name, exc)
    chacc_logger.info(f"Python packages for module '{module_name}' are installed.")
    return result.warnings


def _package_error(module_name: str, exc: Exception) -> HTTPException:
    from chacc import ResolutionError

    text = str(exc).strip()
    if getattr(exc, "network", False) or module_packages.looks_like_network_error(text):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Could not reach the package index to install the Python packages of "
                f"'{module_name}'. Nothing was changed. Connect the server to the network and "
                "try again."
            ),
        )
    if isinstance(exc, ResolutionError) and exc.conflicts:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"The Python requirements of '{module_name}' conflict: {text}",
        )
    if isinstance(exc, ResolutionError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"The Python requirements of '{module_name}' can't be resolved: {text}",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Installing the Python packages of '{module_name}' failed: {text}",
    )


def _check_module_dependencies(
    module_name: str, meta: dict, db: Session
) -> tuple[JSONResponse | None, list[str]]:
    """
    Check ``meta``'s declared modules against the modules available in this mode.

    Returns ``(error_response, missing_optional)``. ``error_response`` is a 409
    when a required module is missing; the caller returns it as is. Nothing is
    installed automatically: the user installs the missing modules.
    """
    available = set(available_module_metas(db)) - {module_name}
    missing = missing_dependencies(meta, available)
    if missing.required:
        names = ", ".join(missing.required)
        return (
            JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "detail": (
                        f"Module '{module_name}' requires module(s) that are not installed: "
                        f"{names}. Install them first, then try again."
                    ),
                    "missing_dependencies": {
                        "required": missing.required,
                        "optional": missing.optional,
                    },
                },
            ),
            missing.optional,
        )
    return None, missing.optional


def _optional_warning(module_name: str, missing_optional: list[str]) -> str:
    return (
        f"Optional module(s) not installed: {', '.join(missing_optional)}. "
        f"'{module_name}' works without them, with fewer features."
    )


def _dependents_warning(module_name: str, db: Session) -> list[str]:
    """Warn when other available modules require the module being removed."""
    dependents = dependents_of(module_name, available_module_metas(db))
    if not dependents:
        return []
    return [
        (
            f"Module(s) {', '.join(dependents)} require '{module_name}' and will not be "
            "loaded after the restart until it is installed and enabled again."
        )
    ]


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
    sync_db: Session = Depends(get_db),
    current_user: object | None = Depends(get_current_user_optional),
):
    """
    Installs a new ChaCC API module from an .chacc package.

    The upload is streamed to disk in chunks (never fully buffered in memory)
    and limited to ``MAX_MODULE_UPLOAD_SIZE`` bytes (default 10 MB).
    Refused with 409 if a required module (``module_dependencies.required``)
    is not installed. Resolves Python dependencies BEFORE unzipping to prevent
    inconsistent state. Requires server restart to activate the new module.
    """
    if not file.filename or not file.filename.endswith(".chacc"):
        chacc_logger.error(f"Uploaded file '{file.filename}' is not a .chacc package.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .chacc module packages are allowed.",
        )

    tmp_path = await _stream_upload_to_disk(file, MAX_MODULE_UPLOAD_SIZE)

    try:
        module_name, module_requirements, meta = await run_in_threadpool(
            _read_module_archive, tmp_path
        )

        conflict, missing_optional = _check_module_dependencies(module_name, meta, sync_db)
        if conflict is not None:
            chacc_logger.warning(f"Refused to install '{module_name}': missing required module(s).")
            return conflict
        warnings = [_optional_warning(module_name, missing_optional)] if missing_optional else []

        target_chacc_path = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.chacc")
        # Packages are installed BEFORE the archive is saved, so a failure changes nothing.
        warnings += await _install_module_packages(
            module_name, module_requirements, is_new=not os.path.exists(target_chacc_path)
        )

        # shutil.move is an atomic rename on the same filesystem, copy+delete otherwise.
        await run_in_threadpool(shutil.move, tmp_path, target_chacc_path)
        tmp_path = None
        chacc_logger.info(f"Module archive '{module_name}.chacc' saved to '{target_chacc_path}'.")

        await run_in_threadpool(_extract_module_archive, module_name, target_chacc_path)
        module_status.clear_failure(module_name)  # new code: try again on the next start

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": f"Module '{module_name}' installed/updated successfully. "
                "Restart the server to apply changes "
                f"(POST {API_PREFIX}/system/restart).",
                "warnings": warnings,
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
    The modules this server loads and their status: the installed modules, or
    in development mode the folders in plugins/ (like the dependency graph).
    """
    available = set(available_module_metas(db))
    return {"modules": [_module_summary(view, available) for view in console_modules(db)]}


@modules_router.get("/modules/graph")
async def get_module_graph_endpoint(
    db: Session = Depends(get_db),
    current_user: object | None = Depends(get_current_user_in_production),
):
    """
    Module dependency graph for the current mode: installed archives in
    production, the plugins directory in dev mode. Shows which modules are
    blocked, disabled, or missing, plus the order modules load in.

    Open in development mode. In production it requires a login when the
    authentication module is loaded.
    """
    return graph_payload(db)


@modules_router.get("/modules/{module_name}")
async def get_module_details_endpoint(
    module_name: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: object | None = Depends(get_current_user_optional),
):
    """
    Everything about one module: what it declares (license, homepage, required
    ChaCC version, ...), whether it is running and why not, its routes, the
    modules that use it, its Python packages, its archive and its README.
    """
    from src.module_details import module_details

    module = await run_in_threadpool(find_module, db, module_name)
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")
    return await run_in_threadpool(module_details, module, db, request.app)


def _module_summary(module: ModuleView, available: set[str]) -> dict:
    try:
        required, optional = declared_dependencies(module.meta)
        missing = missing_dependencies(module.meta, available - {module.name})
    except DependencyDeclarationError:
        required, optional, missing = [], [], None
    return {
        "name": module.name,
        "display_name": module.display_name,
        "version": module.version,
        "author": module.author,
        "description": module.description,
        "is_enabled": module.is_enabled,
        # "installed": managed from the console; "plugins": a folder in plugins/.
        "source": module.source,
        "is_loaded": module_status.loaded(module.name) is not None,
        # Why it failed to load at startup, if it did.
        "load_failure": (module_status.failure(module.name) or {}).get("reason"),
        "base_path_prefix": module.base_path_prefix,
        "dependencies": {"required": required, "optional": optional},
        "missing_dependencies": {
            "required": missing.required if missing else [],
            "optional": missing.optional if missing else [],
        },
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
    meta_data = module_record.meta_data or {}
    try:
        with (
            zipfile.ZipFile(chacc_filepath, "r") as zip_ref,
            zip_ref.open("module_meta.json") as meta_file,
        ):
            meta_data = json.load(meta_file)
            actual_module_name = meta_data.get("name", module_name)
    except (zipfile.BadZipFile, json.JSONDecodeError, OSError) as e:
        chacc_logger.warning(f"Could not read module_meta.json from {chacc_filepath}: {e}")

    try:
        conflict, missing_optional = _check_module_dependencies(actual_module_name, meta_data, db)
    except DependencyDeclarationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid module_meta.json: {exc}"
        )
    if conflict is not None:
        return conflict
    warnings = [_optional_warning(actual_module_name, missing_optional)] if missing_optional else []

    module_requirements = {}
    try:
        with zipfile.ZipFile(chacc_filepath, "r") as zip_ref:
            content = read_archive_requirements(zip_ref, meta_data)
            if content is not None:
                module_requirements[actual_module_name] = content
    except (zipfile.BadZipFile, OSError) as e:
        chacc_logger.error(f"Could not read requirements from {module_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not read module requirements: {e}",
        )

    # The module being enabled is resolved with the ones already registered.
    warnings += await _install_module_packages(
        actual_module_name, module_requirements, is_new=False
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
    module_status.clear_failure(actual_module_name)
    chacc_logger.info(
        f"Module '{actual_module_name}' marked as enabled in DB. Please restart the API server to activate."
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": f"Module '{actual_module_name}' enabled. "
            "Please restart the server for changes to take effect.",
            "warnings": warnings,
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

    warnings = _dependents_warning(actual_module_name, db)
    module_record.is_enabled = False
    db.commit()
    db.refresh(module_record)
    chacc_logger.info(
        f"Module '{actual_module_name}' marked as disabled in DB. Please restart the API server to deactivate."
    )
    # Its packages stay installed and registered, so enabling it again works offline.

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": f"Module '{actual_module_name}' disabled. Please restart the server for changes to take effect.",
            "warnings": warnings,
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
    warnings = _dependents_warning(actual_module_name, db)

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
        module_status.forget(actual_module_name)
        chacc_logger.info(f"Module '{actual_module_name}' record deleted from database.")

        # Unregister its requirements (no network). Its packages stay installed.
        try:
            await run_in_threadpool(module_packages.forget_module, actual_module_name, chacc_logger)
        except Exception:
            chacc_logger.exception(f"Could not unregister '{actual_module_name}' requirements.")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": f"Module '{actual_module_name}' uninstalled. Please restart the API server to apply changes.",
                "warnings": warnings,
            },
        )

    except Exception as e:
        db.rollback()
        chacc_logger.exception(f"Error during module uninstall of '{module_name}'.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to uninstall module: {e}. Manual intervention may be required.",
        )
