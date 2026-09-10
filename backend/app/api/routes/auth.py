"""Вход, обновление сессии, выход, профиль.

Токен обновления передаётся в теле, а не в cookie: интерфейс и Telegram Mini App живут
на разных источниках, и cookie между ними не разделяется. Хранит его клиент, отзывает —
сервер (`app.repos.models.auth`).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.adapters.identity import Credentials
from app.api.deps import IdentityProviderDep, SessionDep, SettingsDep
from app.api.security import CurrentUser, create_access_token
from app.services import auth as service
from app.services.auth import ACCESS_TOKEN_LIFETIME

router = APIRouter(tags=["вход"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    """Адрес принимается как есть, без проверки формата.

    Проверять формат при входе — значит уметь не пустить пользователя с адресом,
    который система сама же и завела: наши учётные записи живут на служебном домене,
    и строгая проверка отвергает их. Формат проверяется при создании пользователя,
    там это к месту.
    """

    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(default="")
    new_password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    # S105: это не пароль, а название схемы авторизации из RFC 6750.
    token_type: str = "Bearer"  # noqa: S105
    expires_in: int
    must_change_password: bool


class ProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    locale: str
    timezone: str
    must_change_password: bool


def _client(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("user-agent"), request.client.host if request.client else None


@router.post("/auth/login", response_model=TokenResponse, summary="Вход")
async def login(
    payload: LoginRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    provider: IdentityProviderDep,
) -> TokenResponse:
    user_agent, ip = _client(request)

    established = await service.authenticate(
        session,
        provider,
        Credentials(login=payload.email.strip(), secret=payload.password),
        user_agent=user_agent,
        ip=ip,
    )

    return TokenResponse(
        access_token=create_access_token(established.user, settings),
        refresh_token=established.refresh_token,
        expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
        must_change_password=established.user.must_change_password,
    )


@router.post("/auth/refresh", response_model=TokenResponse, summary="Обновление сессии")
async def refresh(
    payload: RefreshRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    user_agent, ip = _client(request)
    established = await service.refresh(
        session,
        payload.refresh_token,
        user_agent=user_agent,
        ip=ip,
    )

    return TokenResponse(
        access_token=create_access_token(established.user, settings),
        refresh_token=established.refresh_token,
        expires_in=int(ACCESS_TOKEN_LIFETIME.total_seconds()),
        must_change_password=established.user.must_change_password,
    )


@router.post("/auth/logout", status_code=204, summary="Выход")
async def logout(payload: RefreshRequest, session: SessionDep) -> None:
    await service.logout(session, payload.refresh_token)


@router.post("/auth/change-password", status_code=204, summary="Смена пароля")
async def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser,
    session: SessionDep,
) -> None:
    """Доступна и до замены временного пароля — иначе войти было бы некуда."""
    await service.change_password(
        session,
        user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )


@router.get("/me", response_model=ProfileResponse, summary="Текущий пользователь")
async def me(user: CurrentUser) -> ProfileResponse:
    return ProfileResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        locale=user.locale,
        timezone=user.timezone,
        must_change_password=user.must_change_password,
    )
