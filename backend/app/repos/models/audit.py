"""Журнал изменений.

Таблица только на дозапись. Неизменяемость обеспечивает сама база триггером, а не
приложение: журнал, который может подчистить тот же код, что пишет в него, ничего не
доказывает ([ADR-0010](../../../docs/adr/ADR-0010-audit-log.md)).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, UUIDPrimaryKey


class Auditable:
    """Модель, изменения которой попадают в журнал.

    Пометка на классе, а не список имён таблиц в сервисе: список забывают пополнить,
    и запись годами меняется бесследно. Здесь забыть можно только одним способом — не
    унаследовать пометку, и это видно в объявлении модели.
    """

    @property
    def audit_hides_values(self) -> bool:
        """Значения полей в журнал не пишутся — только имена и сам факт изменения.

        По умолчанию `False`: у большинства записей содержимое в журнале полезно.
        Переопределяют его двое — реплика и вложение, — и не ради секретности, а потому,
        что журнал отвечает на вопрос «кто и когда», а не хранит вторую копию текста.

        Свойство раньше называлось `audit_is_classified` и отвечало за гриф. Гриф снят
        ([ADR-0024](../../../docs/adr/ADR-0024-share-externally.md)), механизм остался, и
        имя переименовано вслед за смыслом: имя, которое врёт, хуже отсутствующего.
        """
        return False


class AuditLog(UUIDPrimaryKey, Base):
    """Одна запись журнала.

    `Timestamps` намеренно не используется: у неизменяемой записи `updated_at` — поле,
    которое никогда не заполнится, а `created_at` называется здесь `occurred_at`, потому
    что это время события, а не время строки.
    """

    __tablename__ = "audit_log"

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Пользователь может быть удалён из системы, а запись журнала — нет: ссылка
    # обнуляется, но строка остаётся. ON DELETE CASCADE здесь означал бы, что удаление
    # учётной записи стирает след её действий.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_kind: Mapped[str] = mapped_column(String(20), nullable=False)

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)

    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Связывает запись со строкой лога приложения: по одному идентификатору находится и
    # то, что пользователь изменил, и то, что при этом происходило внутри.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        # История одной записи — основной запрос: «что происходило с этим проектом».
        Index(
            "ix_audit_log_entity_type_entity_id_occurred_at",
            "entity_type",
            "entity_id",
            "occurred_at",
        ),
        # Лента изменений за период — второй: «что изменилось со вчера» (ORB-030).
        Index("ix_audit_log_occurred_at", "occurred_at"),
    )
