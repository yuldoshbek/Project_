"""Токены обновления.

Хранятся на сервере, а не только у клиента. Без этого «выход» не существует как
действие: подписанный токен остаётся годным до истечения срока, сколько бы раз
пользователь ни нажал «выйти». Для системы, где двое пользователей и один из них —
заместитель директора, это не мелочь.

Хранится хеш, а не сам токен: утечка базы не должна давать возможность входить.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey


class RefreshToken(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Какой токен пришёл на смену этому.

    Позволяет отличить обычную ротацию от повторного использования уже потраченного
    токена. Второе означает, что токен у кого-то ещё, и правильная реакция — отозвать
    всю цепочку, а не только предъявленный.
    """

    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    __table_args__ = (
        # Выборка действующих токенов пользователя — при каждом обновлении и при выходе.
        Index("ix_refresh_tokens_user_id_expires_at", "user_id", "expires_at"),
    )
