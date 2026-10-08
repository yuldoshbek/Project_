"""Стенд e2e пересоздаёт базу целиком — и потому трогает только свою.

1. База стенда — `*_e2e`, собранная из частей: проходит.
2. База разработки, готовая строка подключения (облако, сервер) и рабочий контур — отказ
   до любого подключения: удалить чужую базу стенд не может даже по ошибке окружения.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.e2e_stand import _refuse_foreign
from app.settings import MIN_SECRET_LENGTH, Settings


def build(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "env": "development",
        "session_secret": SecretStr("к" * MIN_SECRET_LENGTH),
        "jobs_secret": SecretStr("jobs-secret-for-tests"),
        "database_url": None,
        "db_name": "orbita_e2e",
        "_env_file": None,
    }
    return Settings(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_the_stand_database_passes() -> None:
    _refuse_foreign(build())


@pytest.mark.parametrize(
    "overrides",
    [
        {"db_name": "orbita"},
        {"database_url": "postgresql://orbita:secret@db.example/orbita_e2e"},
        {"env": "production"},
    ],
    ids=["база разработки", "готовая строка подключения", "рабочий контур"],
)
def test_any_other_database_is_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(SystemExit):
        _refuse_foreign(build(**overrides))
