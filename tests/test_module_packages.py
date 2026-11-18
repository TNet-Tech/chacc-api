"""Module Python packages: packages directory, core constraints, installs and the boot check."""

import base64
import hashlib
import importlib.metadata
import io
import json
import logging
import sys
import zipfile

import pytest
from chacc.utils import calculate_module_hash
from fastapi.testclient import TestClient

from src import module_packages as mp
from src.module_graph import check_graph

log = logging.getLogger("test-module-packages")


@pytest.fixture
def pkgdir(tmp_path, monkeypatch):
    """Production layout with its own packages directory, cache and status file."""
    target = tmp_path / "packages"
    target.mkdir()
    monkeypatch.setattr(mp, "MODULE_PACKAGES_DIR", str(target))
    monkeypatch.setattr(mp, "STATUS_FILE", str(tmp_path / "deps_status.json"))
    monkeypatch.setattr(mp, "CORE_CONSTRAINTS_FILE", str(tmp_path / "core-constraints.txt"))
    monkeypatch.setattr(mp, "DEVELOPMENT_MODE", False)
    monkeypatch.setattr(mp, "CHACC_BOOT_INSTALL", "missing")
    yield target
    if str(target) in sys.path:
        sys.path.remove(str(target))


def make_wheel(directory, name, version, module_code="VALUE = 1\n"):
    """Build a minimal pure-Python wheel by hand (no network, no build backend)."""
    dist = f"{name}-{version}.dist-info"
    files = {
        f"{name}/__init__.py": module_code,
        f"{dist}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        f"{dist}/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record_lines = []
    for path, content in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content.encode()).digest()).rstrip(b"=")
        record_lines.append(f"{path},sha256={digest.decode()},{len(content.encode())}")
    record_lines.append(f"{dist}/RECORD,,")
    files[f"{dist}/RECORD"] = "\n".join(record_lines) + "\n"
    path = directory / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as zf:
        for name_in_zip, content in files.items():
            zf.writestr(name_in_zip, content)
    return path


class FakeManager:
    """Stands in for chacc.DependencyManager; records what boot asks of it."""

    def __init__(self, cache):
        self.cache = cache
        self.resolved = []
        self.removed = []
        self.last_conflicts = []

    def load_cache(self):
        return self.cache

    def resolve_dependencies_sync(self, requirements, install=True):
        self.resolved.append(requirements)
        raise RuntimeError("Failed to establish a new connection")

    def remove_module(self, name):
        self.removed.append(name)
        return True


def cache_for(modules: dict[str, tuple[str, dict]]):
    """modules: name -> (requirements text, {package: spec})."""
    pins, caches = {}, {}
    for name, (content, packages) in modules.items():
        pins.update(packages)
        caches[name] = {"hash": calculate_module_hash(name, content), "packages": packages}
    return {"requirements_caches": caches, "resolved_packages": pins}


# ---------- Core constraints ----------


def test_core_versions_follow_chacc_api_dependencies():
    versions = mp.core_versions()
    assert versions["fastapi"] == importlib.metadata.version("fastapi")
    # Extras are followed: sqlalchemy[asyncio] needs greenlet.
    assert "greenlet" in versions


def test_core_constraints_file_pins_installed_versions(pkgdir):
    path = mp.write_core_constraints()
    with open(path) as f:
        lines = f.read().splitlines()
    assert f"fastapi=={importlib.metadata.version('fastapi')}" in lines


# ---------- Planning and installing ----------


def test_plan_skips_core_packages_and_reports_stale_ones(pkgdir, monkeypatch):
    monkeypatch.setattr(mp, "site_versions", lambda: {"fastapi": "1.0", "pydantic": "2.0"})
    monkeypatch.setattr(mp, "target_versions", lambda: {"qrcode": "8.0"})
    plan = mp.plan_install(
        {"fastapi": "==1.0", "pydantic": "==1.9", "qrcode": "==8.0", "pillow": "==11.0"}
    )
    assert plan.to_install == ["pillow==11.0"]
    assert plan.stale_core == ["pydantic==1.9 (core has 2.0)"]


def test_install_uses_no_deps_target(pkgdir, monkeypatch):
    calls = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return Done()

    monkeypatch.setattr(mp.subprocess, "run", fake_run)
    mp.install_into_target(["pillow==11.0"], log)
    cmd = calls[0]
    assert "--no-deps" in cmd and cmd[cmd.index("--target") + 1] == str(pkgdir)
    assert mp.recorded_environment() == mp.current_environment()


def test_install_failure_offline_is_a_network_error(pkgdir, monkeypatch):
    class Failed:
        returncode, stdout = 1, ""
        stderr = "WARNING: Retrying ... NewConnectionError: Failed to establish a new connection"

    monkeypatch.setattr(mp.subprocess, "run", lambda cmd, **k: Failed())
    with pytest.raises(mp.PackageInstallError) as exc:
        mp.install_into_target(["pillow==11.0"], log)
    assert exc.value.network


def test_real_install_into_packages_dir_is_importable_after_core(pkgdir, tmp_path):
    wheel = make_wheel(tmp_path, "chacc_t5probe", "1.0")
    mp.install_into_target([str(wheel)], log)
    assert mp.target_versions()["chacc-t5probe"] == "1.0"

    mp.activate()
    assert sys.path.index(str(pkgdir)) > max(
        i for i, p in enumerate(sys.path) if p.endswith("site-packages") and str(pkgdir) not in p
    )
    import chacc_t5probe

    assert chacc_t5probe.VALUE == 1
    sys.modules.pop("chacc_t5probe", None)

    # Reinstalling another version replaces it cleanly (one dist-info left).
    wheel2 = make_wheel(tmp_path, "chacc_t5probe", "2.0", "VALUE = 2\n")
    mp.install_into_target([str(wheel2)], log)
    infos = [p.name for p in pkgdir.iterdir() if p.name.endswith(".dist-info")]
    assert infos == ["chacc_t5probe-2.0.dist-info"]


# ---------- Boot ----------


def test_boot_does_nothing_when_everything_is_installed(pkgdir, monkeypatch):
    fake = FakeManager(cache_for({"menu": ("qrcode\n", {"qrcode": "==8.0"})}))
    monkeypatch.setattr(mp, "manager", lambda logger, **k: fake)
    monkeypatch.setattr(mp, "site_versions", dict)
    monkeypatch.setattr(mp, "target_versions", lambda: {"qrcode": "8.0"})
    monkeypatch.setattr(mp, "install_into_target", lambda *a, **k: pytest.fail("pip was called"))

    report = mp.boot_check({"menu": "qrcode\n"}, log)
    assert report.blocked == {} and fake.resolved == []
    with open(mp.STATUS_FILE) as f:
        assert json.load(f)["ok"] is True


def test_boot_offline_blocks_only_modules_missing_packages(pkgdir, monkeypatch):
    fake = FakeManager(
        cache_for(
            {
                "menu": ("qrcode\n", {"qrcode": "==8.0"}),
                "outbound": ("aiosmtplib\n", {"aiosmtplib": "==3.0"}),
            }
        )
    )
    monkeypatch.setattr(mp, "manager", lambda logger, **k: fake)
    monkeypatch.setattr(mp, "site_versions", dict)
    monkeypatch.setattr(mp, "target_versions", lambda: {"aiosmtplib": "3.0"})
    attempts = []

    def offline_install(specs, logger, **kwargs):
        attempts.append((specs, kwargs))
        raise mp.PackageInstallError("NewConnectionError", network=True)

    monkeypatch.setattr(mp, "install_into_target", offline_install)

    report = mp.boot_check({"menu": "qrcode\n", "outbound": "aiosmtplib\n"}, log)
    assert list(report.blocked) == ["menu"] and "qrcode" in report.blocked["menu"]
    # One quick attempt, never a resolve of already-resolved modules.
    assert len(attempts) == 1 and attempts[0][1]["retries"] == 1
    assert fake.resolved == []


def test_boot_never_calls_pip_when_disabled(pkgdir, monkeypatch):
    monkeypatch.setattr(mp, "CHACC_BOOT_INSTALL", "never")
    fake = FakeManager(cache_for({"menu": ("qrcode\n", {"qrcode": "==8.0"})}))
    monkeypatch.setattr(mp, "manager", lambda logger, **k: fake)
    monkeypatch.setattr(mp, "site_versions", dict)
    monkeypatch.setattr(mp, "target_versions", dict)
    monkeypatch.setattr(mp, "install_into_target", lambda *a, **k: pytest.fail("pip was called"))
    assert "menu" in mp.boot_check({"menu": "qrcode\n"}, log).blocked


def test_boot_installs_missing_packages_when_online(pkgdir, monkeypatch):
    fake = FakeManager(cache_for({"menu": ("qrcode\n", {"qrcode": "==8.0"})}))
    monkeypatch.setattr(mp, "manager", lambda logger, **k: fake)
    monkeypatch.setattr(mp, "site_versions", dict)
    installed = {}
    monkeypatch.setattr(mp, "target_versions", lambda: dict(installed))
    monkeypatch.setattr(
        mp, "install_into_target", lambda specs, logger, **k: installed.update(qrcode="8.0")
    )
    report = mp.boot_check({"menu": "qrcode\n"}, log)
    assert report.blocked == {} and report.installed == ["qrcode==8.0"]


def test_boot_unresolved_module_uses_installed_packages_or_is_blocked(pkgdir, monkeypatch):
    fake = FakeManager({"requirements_caches": {}, "resolved_packages": {}})
    monkeypatch.setattr(mp, "manager", lambda logger, **k: fake)
    report = mp.boot_check(
        {"uses_core": "fastapi\n", "needs_new": "chacc-not-a-real-package>=1\n"}, log
    )
    assert fake.resolved  # one attempt to resolve the unresolved modules
    assert list(report.blocked) == ["needs_new"]
    assert any("uses_core" in w for w in report.warnings)


def test_boot_blocks_when_python_version_changed(pkgdir, monkeypatch):
    (pkgdir / mp.ENV_MARKER_NAME).write_text(
        json.dumps({**mp.current_environment(), "python": "2.7"})  # never the running version
    )
    monkeypatch.setattr(mp, "CHACC_BOOT_INSTALL", "never")
    fake = FakeManager(cache_for({"menu": ("qrcode\n", {"qrcode": "==8.0"})}))
    monkeypatch.setattr(mp, "manager", lambda logger, **k: fake)
    monkeypatch.setattr(mp, "site_versions", dict)
    monkeypatch.setattr(mp, "target_versions", lambda: {"qrcode": "8.0"})
    reason = mp.boot_check({"menu": "qrcode\n"}, log).blocked["menu"]
    assert "Python 2.7" in reason and "chacc deps sync" in reason


def test_blocked_by_packages_propagates_to_dependents():
    metas = {
        "auth": {"name": "auth"},
        "menu": {"name": "menu", "module_dependencies": {"required": ["auth"]}},
        "billing": {"name": "billing"},
    }
    report = check_graph(metas, preblocked={"auth": "Python packages not installed: x"})
    assert set(report.blocked) == {"auth", "menu"}
    assert report.order == ["billing"]


# ---------- Requirements from archives ----------


def test_collect_requirements_reads_archives_without_backbone(tmp_path, monkeypatch):
    from src.module_loader import archive

    monkeypatch.setattr(archive, "MODULES_INSTALLED_DIR", str(tmp_path))
    for name, meta, files in [
        ("menu", {"name": "menu"}, {"requirements.txt": "qrcode\n"}),
        ("auth", {"name": "auth", "dependencies_file": "deps.txt"}, {"deps.txt": "pyjwt\n"}),
        ("bare", {"name": "bare"}, {}),
    ]:
        with zipfile.ZipFile(tmp_path / f"{name}.chacc", "w") as zf:
            zf.writestr("module_meta.json", json.dumps(meta))
            for path, content in files.items():
                zf.writestr(path, content)

    assert archive.collect_module_requirements() == {"menu": "qrcode\n", "auth": "pyjwt\n"}
    assert archive.collect_module_requirements({"auth"}) == {"auth": "pyjwt\n"}


# ---------- Endpoints ----------


def chacc_upload(name="probe", requirements="qrcode\n"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("module_meta.json", json.dumps({"name": name, "version": "1.0.0"}))
        zf.writestr("requirements.txt", requirements)
    buf.seek(0)
    return {"file": (f"{name}.chacc", buf, "application/zip")}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from chacc_api.server.main import app
    from src import modules

    monkeypatch.setattr(modules, "MODULES_INSTALLED_DIR", str(tmp_path / "installed"))
    monkeypatch.setattr(modules, "MODULES_LOADED_DIR", str(tmp_path / "loaded"))
    monkeypatch.setattr(modules, "available_module_metas", lambda db=None, dev=None: {})
    (tmp_path / "installed").mkdir()
    (tmp_path / "loaded").mkdir()
    forgotten = []
    monkeypatch.setattr(mp, "forget_module", lambda name, logger: forgotten.append(name))
    client = TestClient(app)
    client.forgotten = forgotten
    return client


@pytest.mark.parametrize(
    "error, code",
    [
        (lambda: mp.PackageInstallError("NewConnectionError", network=True), 503),
        (
            lambda: __import__("chacc").ResolutionError("conflict", conflicts=[{"package": "x"}]),
            409,
        ),
        (lambda: __import__("chacc").ResolutionError("No matching distribution for nope"), 422),
    ],
)
def test_upload_package_errors_change_nothing(client, tmp_path, monkeypatch, error, code):
    async def failing(requirements, logger):
        raise error()

    monkeypatch.setattr(mp, "resolve_and_install", failing)
    response = client.post("/api/modules/", files=chacc_upload())
    assert response.status_code == code, response.text
    assert list((tmp_path / "installed").iterdir()) == []
    assert client.forgotten == ["probe"]  # a new module is unregistered again


def test_upload_installs_then_saves(client, tmp_path, monkeypatch):
    seen = []

    async def ok(requirements, logger):
        seen.append(requirements)
        return mp.ResolveResult({"qrcode": "==8.0"}, ["a conflict was handled"])

    monkeypatch.setattr(mp, "resolve_and_install", ok)
    response = client.post("/api/modules/", files=chacc_upload())
    assert response.status_code == 200, response.text
    assert seen == [{"probe": "qrcode\n"}]  # no backbone in the set
    assert "a conflict was handled" in response.json()["warnings"]
    assert (tmp_path / "installed" / "probe.chacc").exists()
