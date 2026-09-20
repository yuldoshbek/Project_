"""Действующее лицо запроса.

Вход в систему — это переход по личной ссылке, после которого браузер носит cookie сессии
([ADR-0029](../../../docs/adr/ADR-0029-access-by-link.md)). Экранов входа, паролей и
заголовков, которым верят на слово, в системе нет.

**Проверка стоит в одном месте** — на входе в API: зависимость `get_current_user`
подключена ко всему роутеру данных, а не к каждому пути по отдельности. Путь, который
забыли закрыть, — это ровно то, что нельзя увидеть на ревью.

Роль (помощник или руководитель) приезжает из записи пользователя, а не из запроса. Она
подписывает действие в журнале и ограничивает запись, но ничего не прячет: оба пользователя
видят всё (ADR-0011).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request

from app.api.deps import SessionDep, SettingsDep
from app.domain.access import SESSION_COOKIE
from app.domain.audit import ActorKind
from app.domain.errors import NotAuthenticatedError, PermissionDeniedError
from app.domain.people import Role
from app.repos.models import User
from app.services import access
from app.services.audit import Actor, set_actor


async def get_current_user(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    """Пользователь, от имени которого идёт запрос.

    Запись читается из базы, а не собирается из cookie: у автора записи в журнале должен
    быть настоящий идентификатор, иначе журнал ссылается в пустоту.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise NotAuthenticatedError("Откройте ORBITA по своей личной ссылке")

    user = await access.resolve(
        session,
        token=token,
        secret=settings.session_secret.get_secret_value(),
        now=datetime.now(UTC),
    )

    request.state.user_id = str(user.id)

    # Журнал изменений узнаёт действующее лицо отсюда, а не из аргументов сервисов:
    # передавать его через каждый вызов означает однажды его не передать, и изменение
    # будет приписано фоновой задаче (ADR-0010).
    set_actor(
        Actor(
            id=user.id,
            kind=ActorKind.HUMAN,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_active_user(user: CurrentUser) -> User:
    """Псевдоним `CurrentUser`.

    Имя сохранено намеренно: на эту зависимость ссылаются восемь роутеров, а
    переименование тронуло бы их все и ничего не изменило бы по существу.
    """
    return user


ActiveUser = Annotated[User, Depends(get_active_user)]


async def require_assistant(user: ActiveUser) -> User:
    """Действия, изменяющие данные.

    Данные вносит помощник. Руководитель открывает систему, чтобы смотреть и решать, и
    случайная правка того, что он пришёл посмотреть, — единственная ошибка, которую здесь
    можно сделать пальцем.

    Единственное исключение — решение руководителя. Оно проверяется отдельно и явно, а не
    послаблением здесь: исключение должно быть видно в коде.
    """
    if Role(user.role) is not Role.ASSISTANT:
        raise PermissionDeniedError("Изменение данных доступно в режиме помощника")
    return user


Assistant = Annotated[User, Depends(require_assistant)]
