"""Tests for `chacc doctor`."""

import json

from chacc_cli import doctor
from chacc_cli.doctor import FAIL, OK, WARN

STRONG = "Zk3pQ9vL2xW7mR4tY8bN1cD6fG0hJ5sA-extra-entropy"


def _by_name(results):
    return {r.name: r for r in results}


def test_parse_dotenv_handles_comments_quotes_and_export():
    text = "# c\n\nA=1\nexport B = 'two'\nC=\"three\"\nD=four # trailing\nbad line\n"
    assert doctor.parse_dotenv(text) == {"A": "1", "B": "two", "C": "three", "D": "four"}


def test_real_environment_overrides_dotenv(tmp_path):
    (tmp_path / ".env").write_text("SECRET_KEY=from-file\nONLY_FILE=1\n")
    merged = doctor.load_settings(tmp_path, {"SECRET_KEY": "from-env"})
    assert merged["SECRET_KEY"] == "from-env"
    assert merged["ONLY_FILE"] == "1"


def test_python_version_check():
    assert doctor.check_python((3, 12, 1)).status == OK
    old = doctor.check_python((3, 8, 0))
    assert old.status == FAIL
    assert "3.10" in old.message


def test_secret_key_rules_match_production_validator():
    assert doctor.check_secret_key({"SECRET_KEY": STRONG}, dev_mode=False).status == OK
    assert doctor.check_secret_key({}, dev_mode=False).status == FAIL
    assert doctor.check_secret_key({}, dev_mode=True).status == WARN
    short = doctor.check_secret_key({"SECRET_KEY": "abc"}, dev_mode=False)
    assert short.status == FAIL and "characters" in short.message
    placeholder = doctor.check_secret_key({"SECRET_KEY": "dev-" + "x" * 40}, dev_mode=False)
    assert placeholder.status == FAIL and "placeholder" in placeholder.message
    assert "secrets.token_urlsafe" in short.hint


def test_dev_flags_fail_only_in_production():
    flags = {"ENABLE_PLUGIN_HOT_RELOAD": "true"}
    assert doctor.check_production_flags(flags, dev_mode=True).status == OK
    assert doctor.check_production_flags(flags, dev_mode=False).status == FAIL
    assert doctor.check_production_flags({}, dev_mode=False).status == OK


def test_postgres_checks(tmp_path):
    base = {
        "DATABASE_ENGINE": "postgresql",
        "DATABASE_USER": "u",
        "DATABASE_PASSWORD": "p",
        "DATABASE_NAME": "n",
    }
    up = doctor.check_database(base, tmp_path, can_connect=lambda h, p: True)
    down = doctor.check_database(base, tmp_path, can_connect=lambda h, p: False)
    incomplete = doctor.check_database(
        {"DATABASE_ENGINE": "postgresql"}, tmp_path, can_connect=lambda h, p: True
    )
    assert up.status == OK
    assert down.status == FAIL
    assert incomplete.status == FAIL and "DATABASE_USER" in incomplete.message
    bad_port = doctor.check_database({**base, "DATABASE_PORT": "abc"}, tmp_path)
    assert bad_port.status == FAIL


def test_sqlite_directory_must_be_writable(tmp_path):
    assert doctor.check_database({}, tmp_path).status == OK
    blocker = tmp_path / "file"
    blocker.write_text("x")
    bad = doctor.check_database({"SQLITE_DATABASE_PATH": str(blocker / "sub")}, tmp_path)
    assert bad.status == FAIL


def test_redis_is_optional():
    assert doctor.check_redis({}).status == OK
    enabled = {"REDIS_ENABLED": "true"}
    assert doctor.check_redis(enabled, can_connect=lambda h, p: True).status == OK
    assert doctor.check_redis(enabled, can_connect=lambda h, p: False).status == WARN


def test_port_check():
    assert doctor.check_port("0.0.0.0", 8085, port_is_free=lambda h, p: True).status == OK
    busy = doctor.check_port("0.0.0.0", 8085, port_is_free=lambda h, p: False)
    assert busy.status == WARN and "8086" in busy.hint


def test_run_checks_end_to_end_on_clean_dev_folder(tmp_path):
    results = doctor.run_checks(
        cwd=tmp_path, environ={"CHACC_DEV_MODE": "true"}, dev_mode=None, port=65432
    )
    named = _by_name(results)
    assert named["Module folders"].status == OK
    assert named[".env file"].status == WARN
    assert named["SECRET_KEY"].status == WARN
    assert doctor.exit_code(results) == 0
    assert doctor.exit_code(results, strict=True) == 1


def test_report_and_json_are_readable(tmp_path, capsys):
    code = doctor.run_doctor(dev=True, port=65433)
    out = capsys.readouterr().out
    assert "ChaCC doctor" in out
    assert code in (0, 1)
    doctor.run_doctor(as_json=True, dev=True, port=65433)
    data = json.loads(capsys.readouterr().out)
    assert {"name", "status", "message", "hint"} <= set(data[0])
