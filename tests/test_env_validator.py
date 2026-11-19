"""Environment validation: errors stop production; in development they are warnings."""

import logging

import pytest

from src import env_validator
from src.env_validator import EnvironmentValidator, ValidationError

INSECURE_KEY = "dev-secret-key-for-local-testing-only-123"


@pytest.fixture
def records(monkeypatch, caplog):
    monkeypatch.setattr(env_validator, "SECRET_KEY", INSECURE_KEY)
    monkeypatch.setattr(env_validator, "DATABASE_ENGINE", "sqlite")
    monkeypatch.setattr(env_validator, "ENABLE_PLUGIN_HOT_RELOAD", False)
    monkeypatch.setattr(env_validator, "PLUGIN_AUTO_DISCOVERY", False)
    caplog.set_level(logging.INFO, logger=env_validator.chacc_logger.name)
    return caplog


def logged(caplog, level):
    return [r.getMessage() for r in caplog.records if r.levelno == level]


def test_development_logs_problems_as_warnings(monkeypatch, records):
    monkeypatch.setattr(env_validator, "DEVELOPMENT_MODE", True)

    result = EnvironmentValidator().validate()

    assert result["valid"] is False
    assert any("insecure pattern '^dev-'" in e for e in result["errors"])
    assert logged(records, logging.ERROR) == []
    warnings = logged(records, logging.WARNING)
    assert any("'^dev-'" in w and "not allowed in production" in w for w in warnings)
    assert any("would stop the server in production" in w for w in warnings)


def test_production_still_logs_errors_and_refuses(monkeypatch, records):
    monkeypatch.setattr(env_validator, "DEVELOPMENT_MODE", False)

    with pytest.raises(ValidationError, match=r"\^dev-"):
        EnvironmentValidator().validate()

    errors = logged(records, logging.ERROR)
    assert any("'^dev-'" in e for e in errors)
    assert "Environment validation FAILED" in errors


# ---------- Web console key ----------


@pytest.mark.parametrize(
    "key, warned",
    [
        ("", False),  # not set: the console is open, with a warning elsewhere
        ("Short key 你好 !", False),  # any characters
        ("12345678", False),
        ("1234567", True),
    ],
)
def test_console_key_only_warns_when_short(monkeypatch, key, warned):
    monkeypatch.setattr(env_validator, "CONSOLE_KEY", key)
    validator = EnvironmentValidator()
    assert validator.validate_console_key() is True
    assert validator.errors == []
    assert bool(validator.warnings) is warned


def test_short_console_key_never_stops_production(monkeypatch, records):
    monkeypatch.setattr(env_validator, "SECRET_KEY", "Zq8-strong-secret-key-value-for-tests-0001")
    monkeypatch.setattr(env_validator, "CONSOLE_KEY", "1234")
    monkeypatch.setattr(env_validator, "DEVELOPMENT_MODE", False)
    result = EnvironmentValidator().validate()
    assert result["valid"] is True
    assert any("CHACC_CONSOLE_KEY is short" in w for w in logged(records, logging.WARNING))
