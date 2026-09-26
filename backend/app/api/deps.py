"""Зависимости FastAPI.

Роутеры получают сессию и настройки отсюда, а не создают их сами: иначе транзакция
перестаёт совпадать с границей запроса, а в тестах нечего подменить.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.transaction import SESSION_STATE_ATTRIBUTE
from app.repos.database import new_session
from app.settings import Settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Сессия на время запроса. Фиксирует её не эта функция, а маршрут.

    Разбор зависимости с `yield` происходит **после** отправки ответа, поэтому фиксация
    здесь означала бы «создано» для клиента раньше, чем запись увидит следующий запрос
    (`api.transaction` — там замеры и последствия). Фиксирует `CommitOnSuccess`, а сессия
    кладётся в состояние запроса, чтобы он до неё дотянулся.

    Откат остаётся здесь: он нужен на пути с исключением, а на нём маршрут до фиксации не
    доходит.
    """
    async with new_session() as session:
        setattr(request.state, SESSION_STATE_ATTRIBUTE, session)
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_app_settings(request: Request) -> Settings:
    """Настройки того приложения, которое обрабатывает запрос.

    Намеренно не `get_settings()`: тот читает окружение и кеширует результат на процесс.
    Тогда `create_app(settings)` создавал бы приложение, часть которого работает с
    переданными настройками (подключение к базе), а часть — с прочитанными из окружения
    (строка подключения из чужого окружения). Такое расхождение проявляется не в тесте, а в бою.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise RuntimeError("настройки не привязаны к приложению: используйте create_app")
    assert isinstance(settings, Settings)
    return settings


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def is_demo(settings: Settings) -> bool:
    """Показывает ли контур вымышленные данные.

    Они живут везде, кроме рабочего контура (инвариант 11), и экран обязан это сказать:
    иначе вымышленную строку однажды примут за настоящую. Одна функция на все разделы —
    пометка не может стоять на Пульте и пропасть в «Проектах».
    """
    return settings.env != "production"
