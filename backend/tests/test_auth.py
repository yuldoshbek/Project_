"""Вход в систему.

Проверяется не «работает ли JWT», а обещания, которые дороже всего нарушить: отказ
выглядит одинаково независимо от причины, перебор упирается в блокировку, токен
обновления одноразовый, а выход действительно закрывает сессию.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.identity import Credentials, IdentityProvider
from app.adapters.passwords import hash_password, needs_rehash
from app.api.deps import get_identity_provider
from app.api.security import create_access_token
from app.domain.people import Role
from app.repos.models import RefreshToken, User
from app.services import auth as service
from app.settings import Settings

pytestmark = pytest.mark.infra

PASSWORD = "очень-длинный-пароль-2026"
OTHER_PASSWORD = "другой-очень-длинный-пароль"


async def make_user(
    session: AsyncSession,
    *,
    email: str = "ivan@orbita.local",
    password: str | None = PASSWORD,
    role: Role = Role.ASSISTANT,
    is_active: bool = True,
    must_change_password: bool = False,
) -> User:
    user = User(
        email=email,
        full_name="Иван Иванов",
        role=role,
        is_active=is_active,
        must_change_password=must_change_password,
        password_hash=hash_password(password) if password else None,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
async def authorized(
    api: AsyncClient, session: AsyncSession
) -> AsyncIterator[tuple[AsyncClient, User]]:
    """Клиент с действующим токеном доступа."""
    user = await make_user(session)
    response = await api.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    api.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    yield api, user


class TestLogin:
    async def test_correct_password_opens_a_session(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        await make_user(session)

        response = await api.post(
            "/api/v1/auth/login",
            json={"email": "ivan@orbita.local", "password": PASSWORD},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] == 15 * 60

    async def test_unknown_address_and_wrong_password_look_identical(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        """Различие в ответах позволило бы перебором узнать, какие адреса заведены."""
        await make_user(session)

        wrong_password = await api.post(
            "/api/v1/auth/login",
            json={"email": "ivan@orbita.local", "password": "неверный-длинный-пароль"},
        )
        unknown_address = await api.post(
            "/api/v1/auth/login",
            json={"email": "никого@orbita.local", "password": "неверный-длинный-пароль"},
        )

        assert wrong_password.status_code == unknown_address.status_code
        assert wrong_password.json()["type"] == unknown_address.json()["type"]
        assert wrong_password.json()["detail"] == unknown_address.json()["detail"]

    async def test_deactivated_user_cannot_enter(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        """Отключённый пользователь не входит, но остаётся в записях (ORB-007)."""
        await make_user(session, is_active=False)

        response = await api.post(
            "/api/v1/auth/login",
            json={"email": "ivan@orbita.local", "password": PASSWORD},
        )

        assert response.status_code == 403
        assert response.json()["type"].endswith("authentication-failed")

    async def test_account_without_password_cannot_enter(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        """Учётные записи из сидов без пароля: войти нельзя, пока его не назначат."""
        await make_user(session, password=None)

        response = await api.post(
            "/api/v1/auth/login",
            json={"email": "ivan@orbita.local", "password": "любой-длинный-пароль"},
        )

        assert response.status_code == 403

    async def test_login_recomputes_a_hash_made_with_weaker_parameters(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        """Момент входа — единственный, когда у нас есть открытый пароль.

        Параметры хеширования со временем ужесточаются. Без пересчёта база годами
        хранила бы хеши по правилам того дня, когда пароль завели, и ужесточение
        параметров не дошло бы ни до одного существующего пользователя.
        """
        weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
        user = await make_user(session, password=None)
        user.password_hash = weak.hash(PASSWORD)
        await session.flush()
        stale = user.password_hash

        response = await api.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": PASSWORD},
        )

        assert response.status_code == 200
        await session.refresh(user)
        assert user.password_hash != stale
        assert not needs_rehash(user.password_hash)


class TestBruteForceProtection:
    async def test_five_failures_lock_the_account(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        user = await make_user(session)

        for _ in range(service.MAX_FAILED_ATTEMPTS):
            await api.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "неверный-длинный-пароль"},
            )

        await session.refresh(user)
        assert user.failed_login_count == service.MAX_FAILED_ATTEMPTS
        assert user.locked_until is not None

    async def test_lock_holds_even_with_the_right_password(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        """Иначе блокировка не мешала бы перебору, а только раздражала владельца."""
        user = await make_user(session)
        user.locked_until = datetime.now(UTC) + timedelta(minutes=15)
        await session.flush()

        response = await api.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": PASSWORD},
        )

        assert response.status_code == 403
        assert response.json()["type"].endswith("account-locked")

    async def test_expired_lock_lets_the_owner_back_in(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        user = await make_user(session)
        user.locked_until = datetime.now(UTC) - timedelta(minutes=1)
        user.failed_login_count = service.MAX_FAILED_ATTEMPTS
        await session.flush()

        response = await api.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": PASSWORD},
        )

        assert response.status_code == 200

    async def test_successful_login_resets_the_counter(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        user = await make_user(session)
        user.failed_login_count = 3
        await session.flush()

        await api.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})

        await session.refresh(user)
        assert user.failed_login_count == 0
        assert user.locked_until is None


class TestRefreshRotation:
    async def test_refresh_issues_a_new_token_and_retires_the_old(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        await make_user(session)
        first = (
            await api.post(
                "/api/v1/auth/login",
                json={"email": "ivan@orbita.local", "password": PASSWORD},
            )
        ).json()

        second = await api.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": first["refresh_token"]},
        )

        assert second.status_code == 200
        assert second.json()["refresh_token"] != first["refresh_token"]

        reused = await api.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": first["refresh_token"]},
        )
        assert reused.status_code == 403

    async def test_reusing_a_spent_token_closes_every_session(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        """Потраченный токен, предъявленный снова, означает, что он есть у кого-то ещё.

        Правильная реакция — закрыть все сессии, а не только предъявленную: цена ошибки
        здесь несоизмерима с неудобством повторного входа.
        """
        user = await make_user(session)
        first = (
            await api.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": PASSWORD},
            )
        ).json()
        second = (
            await api.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": first["refresh_token"]},
            )
        ).json()

        await api.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})

        still_valid = await api.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": second["refresh_token"]},
        )
        assert still_valid.status_code == 403, "повторное использование обязано закрыть всю цепочку"

        alive = await session.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
            )
        )
        assert list(alive) == []

    async def test_unknown_refresh_token_is_refused(self, api: AsyncClient) -> None:
        """Выдуманный токен неотличим по ответу от потраченного и от истёкшего."""
        response = await api.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "sIkR7Qm2vXo9LpZa4TbNc1EdGh8UwYf3JiKl6MnOpQr"},
        )

        assert response.status_code == 403
        assert "недействительна" in response.json()["detail"]

    async def test_expired_refresh_token_is_refused_with_a_readable_reason(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        """Срок жизни токена обновления — месяц, и он обязан кончаться.

        Иначе «выйти из системы» становится единственным способом закрыть сессию, а
        забытый на чужом устройстве вход живёт вечно.
        """
        user = await make_user(session)
        tokens = (
            await api.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": PASSWORD},
            )
        ).json()

        record = await session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == service.hash_token(tokens["refresh_token"])
            )
        )
        assert record is not None
        record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await session.flush()

        response = await api.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )

        assert response.status_code == 403
        assert "истекла" in response.json()["detail"]

    async def test_deactivated_user_cannot_refresh(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        """Отключение обязано действовать и на обновление, а не только на доступ.

        Иначе отключённый пользователь продлевал бы себе сессию месяц подряд, и
        проверка на каждом запросе (`test_deactivation_takes_effect_immediately`)
        оказалась бы обойдена с другой стороны.
        """
        user = await make_user(session)
        tokens = (
            await api.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": PASSWORD},
            )
        ).json()

        user.is_active = False
        await session.flush()

        response = await api.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )

        assert response.status_code == 403

    async def test_logout_actually_closes_the_session(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        """Без хранения токенов «выход» был бы надписью на кнопке, а не действием."""
        await make_user(session)
        tokens = (
            await api.post(
                "/api/v1/auth/login",
                json={"email": "ivan@orbita.local", "password": PASSWORD},
            )
        ).json()

        logout = await api.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert logout.status_code == 204

        after = await api.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert after.status_code == 403


class TestAccessToken:
    async def test_profile_requires_a_token(self, api: AsyncClient) -> None:
        response = await api.get("/api/v1/me")

        assert response.status_code == 403
        assert response.headers["content-type"].startswith("application/problem+json")

    async def test_profile_returns_the_current_user(
        self, authorized: tuple[AsyncClient, User]
    ) -> None:
        client, user = authorized

        body = (await client.get("/api/v1/me")).json()

        assert body["email"] == user.email
        assert body["role"] == Role.ASSISTANT
        assert body["timezone"] == "Asia/Tashkent"

    async def test_expired_token_is_refused_with_a_readable_reason(
        self, api: AsyncClient, session: AsyncSession, settings: Settings
    ) -> None:
        user = await make_user(session)
        expired = jwt.encode(
            {
                "sub": str(user.id),
                "role": user.role,
                "typ": "access",
                "iat": datetime.now(UTC) - timedelta(hours=2),
                "exp": datetime.now(UTC) - timedelta(hours=1),
            },
            settings.secret_key.get_secret_value(),
            algorithm="HS256",
        )

        response = await api.get("/api/v1/me", headers={"Authorization": f"Bearer {expired}"})

        assert response.status_code == 403
        assert "истёк" in response.json()["detail"]

    async def test_refresh_token_does_not_work_as_access_token(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        """У них разный срок жизни и разное назначение."""
        await make_user(session)
        tokens = (
            await api.post(
                "/api/v1/auth/login",
                json={"email": "ivan@orbita.local", "password": PASSWORD},
            )
        ).json()

        response = await api.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
        )

        assert response.status_code == 403

    async def test_deactivation_takes_effect_immediately(
        self, authorized: tuple[AsyncClient, User], session: AsyncSession
    ) -> None:
        """Запись читается из базы на каждом запросе, а не берётся из подписи.

        Иначе отключённый пользователь работал бы до истечения токена.
        """
        client, user = authorized
        user.is_active = False
        await session.flush()

        assert (await client.get("/api/v1/me")).status_code == 403

    async def test_tampered_token_is_refused(self, api: AsyncClient, session: AsyncSession) -> None:
        user = await make_user(session)
        forged = jwt.encode(
            {"sub": str(user.id), "role": user.role, "typ": "access"},
            # Длина как у настоящего: проверяем подделку подписи, а не длину ключа.
            "чужой-ключ-достаточной-длины-для-подписи-hmac",
            algorithm="HS256",
        )

        response = await api.get("/api/v1/me", headers={"Authorization": f"Bearer {forged}"})

        assert response.status_code == 403


class TestPasswordChange:
    async def test_temporary_password_blocks_everything_except_its_own_change(
        self, api: AsyncClient, session: AsyncSession, settings: Settings
    ) -> None:
        """Проверяется на сервере, а не перенаправлением в интерфейсе.

        Иначе обязательная смена обходится обращением к API напрямую.
        """
        user = await make_user(session, must_change_password=True)
        headers = {"Authorization": f"Bearer {create_access_token(user, settings)}"}

        assert (await api.get("/api/v1/me", headers=headers)).status_code == 200

        blocked = await api.get("/api/v1/dictionaries", headers=headers)
        assert blocked.status_code == 403
        assert blocked.json()["type"].endswith("password-change-required")

        changed = await api.post(
            "/api/v1/auth/change-password",
            headers=headers,
            json={"current_password": PASSWORD, "new_password": OTHER_PASSWORD},
        )
        assert changed.status_code == 204

    async def test_current_password_is_required(self, authorized: tuple[AsyncClient, User]) -> None:
        """Доступ к открытому браузеру не должен означать смену пароля владельца."""
        client, _ = authorized

        response = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "не-тот-пароль-совсем", "new_password": OTHER_PASSWORD},
        )

        assert response.status_code == 403

    async def test_short_password_is_refused_with_an_explanation(
        self, authorized: tuple[AsyncClient, User]
    ) -> None:
        client, _ = authorized

        response = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": PASSWORD, "new_password": "коротко"},
        )

        assert response.status_code == 422
        assert "12" in response.json()["detail"]

    async def test_repeating_the_current_password_is_refused(
        self, authorized: tuple[AsyncClient, User]
    ) -> None:
        client, _ = authorized

        response = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": PASSWORD, "new_password": PASSWORD},
        )

        assert response.status_code == 422

    async def test_change_closes_other_sessions(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        """Пароль меняют в том числе из-за подозрения на утечку.

        Оставить чужую сессию открытой означало бы не сделать ничего.
        """
        user = await make_user(session)
        tokens = (
            await api.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": PASSWORD},
            )
        ).json()

        await api.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={"current_password": PASSWORD, "new_password": OTHER_PASSWORD},
        )

        after = await api.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert after.status_code == 403


class TestProviderSubstitution:
    async def test_another_provider_needs_no_router_changes(
        self, app: FastAPI, api: AsyncClient, session: AsyncSession
    ) -> None:
        """Критерий ORB-006 и обещание ADR-0001.

        Провайдер приходит зависимостью, поэтому подменяется целиком — и на месте
        локального входа завтра окажется SETA, без единой правки в роутерах.
        """
        user = await make_user(session, email="seta@orbita.local", password=None)

        class AlwaysAllows:
            name = "тестовый"

            async def authenticate(
                self, _session: AsyncSession, _credentials: Credentials
            ) -> User | None:
                return user

        provider: IdentityProvider = AlwaysAllows()
        app.dependency_overrides[get_identity_provider] = lambda: provider
        try:
            response = await api.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "пароль-провайдер-не-смотрит"},
            )
        finally:
            app.dependency_overrides.pop(get_identity_provider, None)

        assert response.status_code == 200
        assert response.json()["access_token"]
