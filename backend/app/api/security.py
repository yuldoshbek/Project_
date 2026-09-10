"""Токен доступа и определение текущего пользователя.

Токен доступа — подписанный JWT с коротким сроком жизни, он не хранится на сервере.
Долгоживущий токен обновления, наоборот, хранится и отзывается
(`app.repos.models.auth`): иначе «выход» не существует как действие.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import SessionDep, SettingsDep
from app.domain.audit import ActorKind
from app.domain.errors import NotAuthenticatedError, PermissionDeniedError
from app.domain.people import Role
from app.repos.models import User
from app.services.audit import Actor, set_actor
from app.services.auth import ACCESS_TOKEN_LIFETIME
from app.settings import Settings

ALGORITHM = "HS256"
TOKEN_TYPE = "access"  # noqa: S105  — это назначение токена, а не пароль

# auto_error=False: без него FastAPI отдаёт свой ответ 401, минуя наш формат RFC 9457,
# и клиент получает две разные формы ошибки от одного API.
bearer_scheme = HTTPBearer(auto_error=False)


class PasswordChangeRequiredError(PermissionDeniedError):
    """Пароль выдан администратором и ещё не заменён.

    Проверяется на сервере, а не только перенаправлением в интерфейсе: иначе
    обязательная смена пароля обходится обращением к API напрямую.
    """

    code = "password-change-required"


def create_access_token(user: User, settings: Settings) -> str:
    """Токен доступа.

    Утверждение `role` в теле токена — **справочное**. Сервер его не читает: роль
    берётся из базы на каждом запросе (`require_assistant`), иначе смена роли и
    отключение пользователя действовали бы только после истечения токена. Клали его
    ради интерфейса — он рисует экран под роль, не дожидаясь ответа `/me`.

    Подписанное утверждение, которому не верят, — ловушка для следующего читателя:
    однажды его примут за проверенное. Проверка обратного — в `test_roles.py`,
    `test_role_claim_in_the_token_does_not_grant_anything` (ORB-053).
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "role": user.role,
        "typ": TOKEN_TYPE,
        "iat": now,
        "exp": now + ACCESS_TOKEN_LIFETIME,
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
        )
    except jwt.ExpiredSignatureError as error:
        raise NotAuthenticatedError(
            "Срок действия сессии истёк, обновите её или войдите заново"
        ) from error
    except jwt.InvalidTokenError as error:
        raise NotAuthenticatedError("Недействительный токен доступа") from error

    if claims.get("typ") != TOKEN_TYPE:
        # Токен обновления не должен работать как токен доступа: у него другой срок
        # жизни и другое назначение.
        raise NotAuthenticatedError("Недействительный токен доступа")

    return claims


async def get_current_user(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Текущий пользователь.

    Запись читается из базы на каждом запросе, а не берётся из токена. Токен живёт
    пятнадцать минут — этого достаточно, чтобы отключённый пользователь успел поработать,
    если верить только подписи.
    """
    if credentials is None:
        raise NotAuthenticatedError("Требуется вход в систему")

    claims = decode_access_token(credentials.credentials, settings)

    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except ValueError as error:
        raise NotAuthenticatedError("Недействительный токен доступа") from error

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise NotAuthenticatedError("Требуется вход в систему")

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
    """Пользователь, которому доступна работа с данными.

    Пока временный пароль не заменён, открыты только `GET /me` и смена пароля.
    """
    if user.must_change_password:
        raise PasswordChangeRequiredError("Сначала смените временный пароль")
    return user


ActiveUser = Annotated[User, Depends(get_active_user)]


async def require_assistant(user: ActiveUser) -> User:
    """Действия, изменяющие данные.

    Руководителю доступно ровно одно исключение — решение по проекту на контроле
    ([ADR-0011](../../../docs/adr/ADR-0011-two-user-scope.md)). Оно проверяется отдельно
    и явно, а не через послабление здесь: исключение должно быть видно в коде.
    """
    if Role(user.role) is not Role.ASSISTANT:
        raise PermissionDeniedError("Изменение данных доступно только помощнику")
    return user


Assistant = Annotated[User, Depends(require_assistant)]
