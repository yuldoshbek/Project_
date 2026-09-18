"""Действующее лицо запроса. Входа в систему нет.

Вход снят решением заказчика 18.09.2026 (ADR-0026): пользователей двое, границы между
ними нет (ADR-0011), и экран входа охранял не их друг от друга, а систему от внешнего
мира — то есть делал работу периметра, стоя внутри приложения. Периметром теперь
занимается обратный прокси на сервере агентства, а приложение занимается делом.

Роль осталась, потому что у неё две задачи, не связанные с защитой:

1. У записи в `audit_log` обязан быть автор (инвариант 4, ADR-0010). «Система» вместо
   имени через месяц не отвечает на вопрос «кто это отметил».
2. Решение руководителя обязано быть отличимо от заметки помощника — это единственное
   действие, которое в системе есть у руководителя.

**Сервер верит заголовку на слово, и это не недосмотр.** Заголовок не охраняет данные, он
подписывает действие. Подпись, которую легко подделать, бесполезна против злоумышленника и
достаточна против забывчивости — а здесь стоит денег именно забывчивость.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select

from app.api.deps import SessionDep
from app.domain.audit import ActorKind
from app.domain.errors import NotFoundError, PermissionDeniedError
from app.domain.people import Role
from app.repos.models import User
from app.services.audit import Actor, set_actor

ACTOR_HEADER = "X-Orbita-Actor"


def read_role(request: Request) -> Role:
    """Роль из заголовка. Нет заголовка — помощник.

    Помощник по умолчанию, а не руководитель: данные вносит он, и ошибка в его сторону
    безопаснее. Приняв за руководителя того, кто им не представился, мы приписали бы ему
    чужие правки в журнале.

    Неизвестное значение — тоже помощник, без ошибки: заголовок не охраняет вход, и
    ронять запрос из-за опечатки в нём значит воспроизвести вход под другим именем.
    """
    raw = (request.headers.get(ACTOR_HEADER) or "").strip().lower()
    try:
        return Role(raw)
    except ValueError:
        return Role.ASSISTANT


async def get_current_user(request: Request, session: SessionDep) -> User:
    """Пользователь, от имени которого идёт запрос.

    Запись читается из базы, а не собирается из заголовка: у автора записи в журнале
    должен быть настоящий идентификатор, иначе `audit_log` ссылается в пустоту.
    """
    role = read_role(request)
    user = await session.scalar(select(User).where(User.role == role.value, User.is_active))
    if user is None:
        # Сиды не загружены: это поломка развёртывания, а не ошибка запроса.
        raise NotFoundError(f"В системе нет пользователя с ролью «{role.value}»: загрузите сиды")

    request.state.user_id = str(user.id)

    # Журнал изменений узнаёт действующее лицо отсюда, а не из аргументов сервисов:
    # передавать его через каждый вызов означает однажды его не передать, и изменение
    # будет приписано фоновому заданию (ADR-0010).
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

    Имя сохранено намеренно: раньше здесь стоял запрет работать с временным паролем, и
    на эту зависимость ссылаются восемь роутеров. Переименование тронуло бы их все и
    ничего бы не изменило по существу.
    """
    return user


ActiveUser = Annotated[User, Depends(get_active_user)]


async def require_assistant(user: ActiveUser) -> User:
    """Действия, изменяющие данные.

    Это не защита — заголовок роли подделывается тривиально, и ADR-0026 говорит об этом
    прямо. Это защита от промаха: руководитель, открывший систему в режиме просмотра, не
    должен случайно изменить данные, которые он пришёл смотреть.

    Единственное исключение — решение по проекту на контроле
    ([ADR-0011](../../../docs/adr/ADR-0011-two-user-scope.md)). Оно проверяется отдельно
    и явно, а не через послабление здесь: исключение должно быть видно в коде.
    """
    if Role(user.role) is not Role.ASSISTANT:
        raise PermissionDeniedError("Изменение данных доступно в режиме помощника")
    return user


Assistant = Annotated[User, Depends(require_assistant)]
