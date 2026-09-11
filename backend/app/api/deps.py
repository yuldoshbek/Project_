"""Зависимости FastAPI.

Роутеры получают сессию и настройки отсюда, а не создают их сами: иначе транзакция
перестаёт совпадать с границей запроса, а в тестах нечего подменить.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.identity import IdentityProvider, create_identity_provider
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
    (адрес Redis). Такое расхождение проявляется не в тесте, а в бою.
    """
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise RuntimeError("настройки не привязаны к приложению: используйте create_app")
    assert isinstance(settings, Settings)
    return settings


def get_identity_provider(request: Request) -> IdentityProvider:
    """Провайдер установления личности из настроек приложения.

    Зависимость, а не прямой вызов в роутере: так реализацию подменяют и в тестах, и
    при переходе на SETA — не трогая ни один роутер (критерий ORB-006, ADR-0001).
    """
    return create_identity_provider(get_app_settings(request).identity_provider)


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
IdentityProviderDep = Annotated[IdentityProvider, Depends(get_identity_provider)]
