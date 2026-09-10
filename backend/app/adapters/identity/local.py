"""Локальный вход: адрес и пароль.

Реализация по умолчанию. Работает, пока у SETA нет API (ADR-0001, ADR-0013).
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.identity import Credentials
from app.adapters.passwords import hash_password, needs_rehash, verify_password
from app.repos.models import User

logger = structlog.get_logger(__name__)


class LocalIdentityProvider:
    """Проверяет пароль по хешу в базе."""

    name = "local"

    async def authenticate(self, session: AsyncSession, credentials: Credentials) -> User | None:
        user = await session.scalar(select(User).where(User.email == credentials.login))

        # Пароль проверяется даже когда пользователя нет: `verify_password` в этом случае
        # сверяется с заглушкой и тратит столько же времени. Без этого по времени ответа
        # перебором выясняется, какие адреса заведены.
        password_matches = verify_password(
            credentials.secret,
            user.password_hash if user else None,
        )

        if user is None or not password_matches:
            return None

        if not user.is_active:
            # Отключённый пользователь не входит, но остаётся в истории (ORB-007).
            logger.info("login_rejected_inactive", user_id=str(user.id))
            return None

        if user.password_hash and needs_rehash(user.password_hash):
            # Параметры хеширования со временем ужесточаются. Момент входа — единственный,
            # когда у нас есть открытый пароль, чтобы пересчитать хеш.
            user.password_hash = hash_password(credentials.secret)

        return user
