from pathlib import Path

from backend.settings import BASE_DIR, settings


def test_database_path_resolves_relative_to_project_root(monkeypatch):
    monkeypatch.setenv("SCADA_DB_PATH", "data/test_historian.db")
    assert settings.database_path == BASE_DIR / "data" / "test_historian.db"


def test_database_path_preserves_absolute_path(monkeypatch, tmp_path):
    target = tmp_path / "historian.db"
    monkeypatch.setenv("SCADA_DB_PATH", str(target))
    assert settings.database_path == target


def test_control_writes_are_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SCADA_ENABLE_CONTROL_WRITES", raising=False)
    assert settings.control_writes_enabled is False


def test_control_writes_require_explicit_environment_flag(monkeypatch):
    monkeypatch.setenv("SCADA_ENABLE_CONTROL_WRITES", "true")
    assert settings.control_writes_enabled is True
