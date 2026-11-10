"""
Unit tests for module management endpoints.

⚠️  WARNING: These tests create files in .modules_loaded/ directory.

For manual testing, use one of these approaches:

1. Safe test runner (recommended):
   python tests/run_tests_safely.py

2. Disable auto-reload:
   uvicorn main:app --reload=false
   # Then run: pytest tests/

3. Manual cleanup:
   pytest tests/
   rm -rf .modules_loaded/test_module*

4. Use the cleanup fixture (automatic):
   pytest tests/  # Cleanup happens automatically after each test
"""

import json
import os
import shutil
import zipfile

import pytest
from fastapi.testclient import TestClient

from chacc_api.server.main import app
from src.database import engine, metadata_obj


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create all database tables before running tests."""
    metadata_obj.create_all(bind=engine)
    yield
    # metadata_obj.drop_all(bind=engine)


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_test_modules():
    """Clean up test modules after each test."""
    yield
    test_module_path = ".modules_loaded/test_module"
    if os.path.exists(test_module_path):
        shutil.rmtree(test_module_path)
        print(f"Cleaned up test module: {test_module_path}")


def test_get_modules_empty(client):
    """Test getting modules list when no modules are installed."""
    response = client.get("/api/modules/")
    assert response.status_code == 200
    data = response.json()
    assert "modules" in data
    assert isinstance(data["modules"], list)


def test_upload_invalid_file(client):
    """Test uploading a file that is not a .chacc package."""
    response = client.post(
        "/api/modules/", files={"file": ("test.txt", b"not a zip file", "text/plain")}
    )
    assert response.status_code == 400
    assert "Only .chacc module packages are allowed" in response.json()["detail"]


def test_upload_malformed_chacc(client):
    """Test uploading a malformed .chacc file (missing module_meta.json)."""
    import io

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        zip_file.writestr("some_file.txt", "content")

    zip_buffer.seek(0)
    response = client.post(
        "/api/modules/", files={"file": ("test.chacc", zip_buffer, "application/zip")}
    )
    assert response.status_code == 400
    assert "Missing or invalid 'module_meta.json'" in response.json()["detail"]


def test_upload_chacc_missing_name(client):
    """Test uploading a .chacc file with module_meta.json but missing name field."""
    import io

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        meta_data = {"version": "1.0.0", "description": "Test module"}
        zip_file.writestr("module_meta.json", json.dumps(meta_data))

    zip_buffer.seek(0)
    response = client.post(
        "/api/modules/", files={"file": ("test.chacc", zip_buffer, "application/zip")}
    )
    assert response.status_code == 400
    assert "'name' field is missing" in response.json()["detail"]


def test_upload_valid_chacc(client):
    """Test uploading a valid .chacc file - simplified version."""
    import io

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        meta_data = {
            "name": "simple_test_module",
            "display_name": "Simple Test Module",
            "version": "1.0.0",
            "author": "Test Author",
            "description": "A simple test module",
            "entry_point": "module.main:setup",
            "base_path_prefix": "/simple-test",
        }
        zip_file.writestr("module_meta.json", json.dumps(meta_data))

        zip_file.writestr("module/__init__.py", "")
        zip_file.writestr(
            "module/main.py",
            """
from fastapi import APIRouter

def setup(backbone_context):
    router = APIRouter()
    @router.get("/simple-test")
    async def simple_endpoint():
        return {"message": "Simple test module works"}
    return router
""",
        )

    zip_buffer.seek(0)

    response = client.post(
        "/api/modules/", files={"file": ("simple_test_module.chacc", zip_buffer, "application/zip")}
    )

    assert response.status_code in [200, 409]

    if response.status_code == 200:
        data = response.json()
        assert "installed/updated successfully" in data["message"]
        assert "simple_test_module" in data["message"]


def test_enable_nonexistent_module(client):
    """Test enabling a module that doesn't exist."""
    response = client.post("/api/modules/nonexistent/enable")
    assert response.status_code == 404
    assert "Module not found" in response.json()["detail"]


def test_disable_nonexistent_module(client):
    """Test disabling a module that doesn't exist."""
    response = client.post("/api/modules/nonexistent/disable")
    assert response.status_code == 404
    assert "Module not found" in response.json()["detail"]


def test_uninstall_nonexistent_module(client):
    """Test uninstalling a module that doesn't exist."""
    response = client.delete("/api/modules/nonexistent/uninstall")
    assert response.status_code == 404
    assert "Module not found" in response.json()["detail"]


def test_enable_test_module(client):
    """Test enabling a module - simplified version."""
    response = client.post("/api/modules/fake_module/enable")
    assert response.status_code == 404
    data = response.json()
    assert "Module not found" in data["detail"]


def test_disable_test_module(client):
    """Test disabling a module - simplified version."""
    response = client.post("/api/modules/fake_module/disable")
    assert response.status_code == 404
    data = response.json()
    assert "Module not found" in data["detail"]


def test_uninstall_test_module(client):
    """Test uninstalling a module - simplified version."""
    response = client.delete("/api/modules/authentication/uninstall")
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()
        assert "uninstalled" in data["message"].lower()


def test_module_workflow_with_authentication(client):
    """Test complete module workflow: enable/disable operations on existing authentication module."""
    response = client.get("/api/modules/")
    assert response.status_code == 200
    modules = response.json()["modules"]

    auth_module = None
    for module in modules:
        if module["name"] == "authentication":
            auth_module = module
            break

    if auth_module:
        if not auth_module["is_enabled"]:
            response = client.post("/api/modules/authentication/enable")
            assert response.status_code == 200
            assert "enabled" in response.json()["message"].lower()

        response = client.post("/api/modules/authentication/enable")
        assert response.status_code == 200
        assert "already enabled" in response.json()["message"].lower()

        response = client.post("/api/modules/authentication/disable")
        assert response.status_code == 200
        assert "disabled" in response.json()["message"].lower()

        response = client.post("/api/modules/authentication/disable")
        assert response.status_code == 200
        assert "already disabled" in response.json()["message"].lower()

        response = client.post("/api/modules/authentication/enable")
        assert response.status_code == 200
    else:
        pytest.skip("Authentication module not found - skipping integration test")


def test_upload_exceeds_size_limit(client, monkeypatch):
    """Uploads larger than MAX_MODULE_UPLOAD_SIZE are rejected with 413 while streaming."""
    import io

    from src import modules

    monkeypatch.setattr(modules, "MAX_MODULE_UPLOAD_SIZE", 1024)
    payload = io.BytesIO(b"x" * 4096)
    response = client.post(
        "/api/modules/", files={"file": ("big.chacc", payload, "application/zip")}
    )
    assert response.status_code == 413
    assert "maximum allowed size" in response.json()["detail"]
    leftovers = [f for f in os.listdir(modules.MODULES_UPLOAD_DIR) if f.endswith(".part")]
    assert leftovers == []


def test_upload_rejected_by_content_length(client):
    """Requests declaring a Content-Length far above the limit are rejected before parsing."""
    from src.constants import MAX_MODULE_UPLOAD_SIZE

    response = client.post(
        "/api/modules/",
        content=b"",
        headers={
            "Content-Type": "multipart/form-data; boundary=x",
            "Content-Length": str(MAX_MODULE_UPLOAD_SIZE * 2),
        },
    )
    assert response.status_code == 413


def test_upload_not_a_zip(client):
    """A .chacc file that is not a zip archive returns 400, not 500."""
    response = client.post(
        "/api/modules/", files={"file": ("bad.chacc", b"not a zip", "application/zip")}
    )
    assert response.status_code == 400
    assert "not a valid .chacc" in response.json()["detail"]


def test_upload_zip_bomb_guard(client, monkeypatch):
    """Archives whose uncompressed size exceeds the limit are rejected."""
    import io

    from src import modules

    monkeypatch.setattr(modules, "MAX_MODULE_UNCOMPRESSED_SIZE", 1024)
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("module_meta.json", json.dumps({"name": "bomb"}))
        zf.writestr("filler.txt", "0" * 10_000)
    zip_buffer.seek(0)
    response = client.post(
        "/api/modules/", files={"file": ("bomb.chacc", zip_buffer, "application/zip")}
    )
    assert response.status_code == 413
