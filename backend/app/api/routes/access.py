"""Вход по личной ссылке и сведения о текущей сессии.

Этот роутер — единственная часть API, доступная без сессии: по ссылке приходит человек, у
которого сессии ещё нет. Всё остальное закрыто зависимостью `get_current_user`.

Почему переход отвечает перенаправлением, а не страницей: ссылку открывают в браузере, и
человек должен оказаться в системе, а не на JSON-ответе. Токен при этом остаётся в истории
браузера ровно один раз и дальше не нужен — работает cookie.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, SettingsDep
from app.api.security import Assistant, CurrentUser
from app.api.transaction import transactional_router
from app.domain.access import SESSION_COOKIE
from app.domain.errors import NotFoundError
from app.domain.people import Role
from app.repos.models import User
from app.services import access

router = transactional_router(prefix="/api", tags=["доступ"])

# Длина строки браузера, которую имеет смысл хранить: дальше идёт перечисление движков,
# ничего не добавляющее к ответу на вопрос «с чего заходили».
USER_AGENT_LIMIT = 300


class CurrentUserResponse(BaseModel):
    """Кто открыл систему. Интерфейс берёт отсюда роль, язык и имя для приветствия."""

    id: str
    full_name: str
    role: Role
    locale: str
    timezone: str
    can_write: bool


class LinkResponse(BaseModel):
    """Свежая ссылка. Показывается один раз тому, кто её выпустил."""

    url: str
    issued_at: datetime


class SessionSummary(BaseModel):
    """Устройство, с которого открыт доступ."""

    user_agent: str | None
    ip: str | None
    last_seen_at: datetime | None
    expires_at: datetime


async def _user_with_role(session: AsyncSession, role: Role) -> User:
    owner = await session.scalar(select(User).where(User.role == role.value, User.is_active))
    if owner is None:
        # Сиды не загружены: это поломка развёртывания, а не ошибка запроса.
        raise NotFoundError(f"В системе нет пользователя с ролью «{role.value}»")
    return owner


@router.get(
    "/access/{token}",
    include_in_schema=False,
    summary="Переход по личной ссылке",
    response_class=RedirectResponse,
)
async def open_by_link(
    token: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> RedirectResponse:
    """Открывает сессию и уводит в приложение.

    Токен нигде не печатается: путь исключён из схемы, а в ответе его нет. Неизвестная
    ссылка отвечает 404 — «такой ссылки нет», без подсказок, чем именно она не подошла.
    """
    opened = await access.open_session(
        session,
        token=token,
        secret=settings.session_secret.get_secret_value(),
        days=settings.session_days,
        now=datetime.now(UTC),
        ip=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:USER_AGENT_LIMIT] or None,
    )

    redirect = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        SESSION_COOKIE,
        opened.token,
        expires=opened.window.expires_at,
        # Три обязательных свойства префикса `__Host-`: без любого из них браузер молча
        # откажется принимать cookie, и вход «не работает без причины».
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
    # Ссылка не должна попасть в поисковый индекс.
    redirect.headers["X-Robots-Tag"] = "noindex, nofollow"
    return redirect


@router.get("/me", response_model=CurrentUserResponse, summary="Кто я")
async def whoami(user: CurrentUser) -> CurrentUserResponse:
    """Первый запрос интерфейса после загрузки: есть ли сессия и кто её открыл."""
    role = Role(user.role)
    return CurrentUserResponse(
        id=str(user.id),
        full_name=user.full_name,
        role=role,
        locale=user.locale,
        timezone=user.timezone,
        can_write=role.can_write,
    )


@router.post(
    "/access/links/{role}",
    response_model=LinkResponse,
    summary="Перевыпустить личную ссылку",
)
async def reissue_link(
    role: Role,
    session: SessionDep,
    settings: SettingsDep,
    user: Assistant,
) -> LinkResponse:
    """Выпускает новую ссылку и гасит прежние сессии этого пользователя.

    Доступно помощнику: он отвечает за доступы и он же отправляет ссылку руководителю.
    Прежняя ссылка перестаёт работать в тот же момент — в этом и смысл кнопки.
    """
    owner = await _user_with_role(session, role)
    issued = await access.issue_link(
        session,
        user=owner,
        secret=settings.session_secret.get_secret_value(),
        base_url=settings.base_url,
        now=datetime.now(UTC),
    )
    return LinkResponse(url=issued.url, issued_at=issued.issued_at)


@router.get(
    "/access/sessions/{role}",
    response_model=list[SessionSummary],
    summary="Устройства с открытым доступом",
)
async def sessions_of(role: Role, session: SessionDep, user: Assistant) -> list[SessionSummary]:
    """Чужой вход виден здесь: устройство, которого быть не должно."""
    owner = await _user_with_role(session, role)
    rows = await access.active_sessions(session, user_id=owner.id, now=datetime.now(UTC))
    return [
        SessionSummary(
            user_agent=row.user_agent,
            ip=row.ip,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
        )
        for row in rows
    ]
