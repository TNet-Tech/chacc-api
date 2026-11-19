"""``chacc install`` refuses modules whose required modules are not installed."""

import json
import zipfile

import pytest

from chacc_cli.commands import _check_module_dependencies
from chacc_cli.installer.paths import Destinations
from chacc_cli.installer.validate import ValidationError, load_and_validate


def module_dir(path, name, required=(), optional=()):
    path.mkdir(parents=True)
    meta = {
        "name": name,
        "entry_point": "x.main:setup",
        "module_dependencies": {"required": list(required), "optional": list(optional)},
    }
    (path / "module_meta.json").write_text(json.dumps(meta))
    return load_and_validate(str(path))


@pytest.fixture
def dest(tmp_path):
    (tmp_path / "plugins").mkdir()
    (tmp_path / "installed").mkdir()
    return Destinations(str(tmp_path / "plugins"), str(tmp_path / "installed"))


def test_dev_checks_plugins_directory(tmp_path, dest):
    menu = module_dir(tmp_path / "src" / "menu", "menu", ["auth"], ["files"])
    with pytest.raises(ValidationError, match="- auth"):
        _check_module_dependencies(menu, dest, "dev")

    module_dir(tmp_path / "plugins" / "auth", "auth")
    assert _check_module_dependencies(menu, dest, "dev") == ["files"]


def test_prod_checks_installed_archives(tmp_path, dest):
    menu = module_dir(tmp_path / "src" / "menu", "menu", ["auth"])
    module_dir(tmp_path / "plugins" / "auth", "auth")  # dev copy does not count in prod
    with pytest.raises(ValidationError, match="not installed"):
        _check_module_dependencies(menu, dest, "prod")

    with zipfile.ZipFile(tmp_path / "installed" / "auth.chacc", "w") as zf:
        zf.writestr("module_meta.json", json.dumps({"name": "auth"}))
    assert _check_module_dependencies(menu, dest, "prod") == []


def test_invalid_declaration_fails_validation(tmp_path):
    path = tmp_path / "bad"
    path.mkdir()
    bad = {"name": "bad", "module_dependencies": {"required": "auth"}}
    (path / "module_meta.json").write_text(json.dumps(bad))
    with pytest.raises(ValidationError, match="module_dependencies"):
        load_and_validate(str(path))
