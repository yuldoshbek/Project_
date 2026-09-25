"""Ссылки доступа и сессии.

Входа в систему нет: у каждого пользователя своя секретная ссылка, переход по которой
открывает сессию на тридцать дней (ADR-0029). В базе от секретов лежат только отпечатки —
правила в `app.domain.access`.

Две таблицы, потому что это два разных срока жизни. Ссылка живёт до перевыпуска и у
пользователя одна. Сессий у него столько, сколько устройств: iPhone, ноутбук, большой
монитор — и каждую надо уметь погасить отдельно.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey
from app.repos.models.audit import Auditable


class AccessLink(Auditable, UUIDPrimaryKey, Timestamps, Base):
    """Личная ссылка пользователя.

    Журналируется: перевыпуск ссылки — это закрытие доступа, и вопрос «кто и когда её
    перевыпустил» возникает ровно тогда, когда что-то пошло не так.
    """

    __tablename__ = "access_links"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    """Ссылка у пользователя одна. Перевыпуск заменяет отпечаток в этой же строке —
    так в «Управлении» не приходится разбираться, какая из трёх ссылок действующая."""

    token_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """Когда выпущена. Показывается в «Управлении» рядом с последним входом."""

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """Сколько раз по ссылке открывали сессию. Чужой вход виден как лишнее число."""

    @property
    def audit_hides_values(self) -> bool:
        """В журнал пишется факт, а не значения.

        Отпечаток — производная от секрета, и место ему в одной таблице, а не в двух.
        """
        return True


class Session(UUIDPrimaryKey, Timestamps, Base):
    """Открытая сессия — одно устройство одного пользователя.

    Не журналируется: сессии открываются и гаснут десятками, и запись каждой в журнал
    изменений утопила бы в нём деловые события. Кто и когда заходил, видно по самой
    таблице.
    """

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    token_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """Погашена досрочно: перевыпуск ссылки гасит все сессии пользователя сразу."""

    # Чем и откуда заходили. Нужно для одного вопроса: «это заходил я или кто-то ещё».
    # Значения приходят от браузера и доверия не имеют — они не проверяются и ни на что
    # не влияют, кроме этой строки в «Управлении».
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    __table_args__ = (
        # Поиск действующих сессий пользователя: гашение при перевыпуске и список
        # устройств в «Управлении».
        Index("ix_sessions_user_id_expires_at", "user_id", "expires_at"),
    )
