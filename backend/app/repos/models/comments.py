"""Комментарии к проектам и задачам.

Одна таблица на оба вида записей, а не `project_comments` и `task_comments`: реплика
устроена одинаково, различается только то, к чему она относится. Две таблицы означали бы
два одинаковых набора запросов и две ленты, которые однажды разойдутся по поведению.

Ссылка на проект или задачу внешним ключом не закрыта — `entity_id` указывает то на одну
таблицу, то на другую, и база такую связь не выразит. Целостность держит удаление: сервис
уносит комментарии вместе с записью, к которой они относились, а тест это стережёт.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.comments import CommentTarget
from app.repos.base import Base, Timestamps, UUIDPrimaryKey
from app.repos.models.audit import Auditable

TARGETS = ", ".join(f"'{target.value}'" for target in CommentTarget)


class Comment(Auditable, UUIDPrimaryKey, Timestamps, Base):
    """Реплика в обсуждении проекта или задачи (ТЗ 6.1, 6.2)."""

    __tablename__ = "comments"

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Автор может быть удалён из системы, а его реплики — нет: ссылка обнуляется, строка
    # остаётся. Иначе удаление учётной записи выбивало бы куски из обсуждения.
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Правка отмечается отдельно от `updated_at`: тот меняется и от мягкого удаления, а
    # читателю важно другое — «этот текст не тот, что был написан сначала».
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Удаление мягкое: см. `app.domain.comments`. Строка остаётся, тело в ленту не выдаётся.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def audit_hides_values(self) -> bool:
        """Текст реплики в журнал изменений не попадает — никогда.

        Журналу он не нужен: «кто и когда» журнал записывает, а «что написано» лежит в
        самой реплике и никуда не девается — удаление мягкое. Вторая копия того же текста
        оказалась бы в таблице, из которой её уже не вычистить: журнал только на
        дозапись, неизменяемость держит триггер базы
        ([ADR-0010](../../../docs/adr/ADR-0010-audit-log.md)). Правило переживает снятие
        грифа ([ADR-0024](../../../docs/adr/ADR-0024-share-externally.md)), потому что
        оно и не было про гриф.
        """
        return True

    __table_args__ = (
        CheckConstraint(f"entity_type IN ({TARGETS})", name="entity_type_is_known"),
        # Лента одной записи — единственный частый запрос: «что обсуждали по этому проекту».
        Index(
            "ix_comments_entity_type_entity_id_created_at", "entity_type", "entity_id", "created_at"
        ),
    )
