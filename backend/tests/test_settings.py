"""Настройки: обязательные значения, сборка DSN, выбор формата логов."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.settings import Settings


def build(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "env": "test",
        "secret_key": SecretStr("secret"),
        "_env_file": None,
    }
    return Settings(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_secret_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без ключа приложение обязано упасть на старте, а не работать вполсилы."""
    monkeypatch.delenv("ORBITA_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "secret_key" in str(error.value)


def test_database_url_is_built_for_asyncpg() -> None:
    settings = build(
        db_host="db.example",
        db_port=5432,
        db_name="orbita",
        db_user="orbita",
        db_password=SecretStr("p@ss"),
    )

    assert settings.database_url == "postgresql+asyncpg://orbita:p@ss@db.example:5432/orbita"


def test_secrets_are_not_printed() -> None:
    """Репозиторий публичный, логи попадают в отчёты — секрет не должен светиться."""
    settings = build(secret_key=SecretStr("очень-секретно"))

    assert "очень-секретно" not in repr(settings)
    assert "очень-секретно" not in str(settings)


def test_console_logs_in_development_json_elsewhere() -> None:
    assert build(env="development").use_json_logs is False
    assert build(env="production").use_json_logs is True
    assert build(env="test").use_json_logs is True


def test_log_format_can_be_forced() -> None:
    assert build(env="development", log_json=True).use_json_logs is True
    assert build(env="production", log_json=False).use_json_logs is False


def test_unknown_variables_are_ignored() -> None:
    """Окружение общее с воркером и ботом: чужие переменные не должны ронять старт."""
    settings = build(some_unknown_variable="значение")

    assert settings.env == "test"
