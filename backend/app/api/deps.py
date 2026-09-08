"""Зависимости FastAPI.

Роутеры получают сессию и настройки отсюда, а не создают их сами: иначе транзакция
перестаёт совпадать с границей запроса, а в тестах нечего подменить.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.database import session_scope
from app.settings import Settings


async def get_session() -> AsyncIterator[AsyncSession]:
    async for session in session_scope():
        yield session


def get_app_settings(request: Request) -> Settings:
    """Настройки того приложения, которое обрабатывает запрос.

    Намеренно не `get_settings()`: тот читает окружение и кеширует результат на процесс.
    Тогда `create_app(settings)` создавал бы приложение, часть которого работает с
    переданными настройками (подключение к базе), а часть — с прочитанными из окружения
    (адрес Redis). Такое расхождение проявляется не в тесте, а в бою.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise RuntimeError("настройки не привязаны к приложению: используйте create_app")
    assert isinstance(settings, Settings)
    return settings


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
