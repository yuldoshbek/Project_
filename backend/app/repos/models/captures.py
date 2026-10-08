"""Записи Захвата — быстрая запись одной кнопкой (ТЗ 7).

Одна строка на каждую запись, какого бы типа она ни была: «Недавние записи» экрана отвечают
на вопрос «а оно сохранилось и куда ушло?», и ответ собирается одним запросом к этой
таблице, а не склейкой задач со входящими.

**Задача и просьба руководителя** уходят в «Задачи» (допущение V17): задача заводится в той
же транзакции, строка здесь ссылается на неё. Эта ссылка и есть пометка «просьба
руководителя» у задачи — происхождение видно на данных (инвариант 6), и столбца у задачи
для этого не заводится.

**Идея, письмо и мероприятие** ждут во входящих, пока не появятся их разделы (блоки 2–3):
там их и разберут. Правки записи экраном не предусмотрены, поэтому версии у неё нет
(инвариант 14).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.capture import CaptureKind
from app.repos.base import Base, Timestamps, UUIDPrimaryKey
from app.repos.models.audit import Auditable

KINDS = ", ".join(f"'{kind.value}'" for kind in CaptureKind)
WORK = ", ".join(f"'{kind.value}'" for kind in CaptureKind if kind.becomes_task)


class Capture(Auditable, UUIDPrimaryKey, Timestamps, Base):
    """Запись Захвата: что записано, кем, когда и куда ушло."""

    __tablename__ = "captures"

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    """Как записано; у задачи и просьбы — название после разбора. «Недавние записи» у них
    показывают название и срок самой задачи (`services.captures`): задачу потом правят в
    «Задачах», а здесь остаётся сказанное в момент записи."""

    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    """Срок задачи и просьбы, срок ответа на письмо, дата мероприятия. День, а не момент:
    у записи входящих срок — день календаря, как у вехи."""

    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    """Кто записал. Экран подписывает запись ролью автора; пользователей двое, и учётные
    записи не удаляются (ADR-0011), поэтому ссылка обязательна."""

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    """Задача, в которую ушла запись. `SET NULL`: запись о том, что было сказано, переживает
    задачу."""

    __table_args__ = (
        CheckConstraint(f"kind IN ({KINDS})", name="kind_is_known"),
        CheckConstraint(f"task_id IS NULL OR kind IN ({WORK})", name="only_work_has_task"),
        # «Недавние записи» — последние по времени; пометка у задачи — по ссылке на неё.
        Index("ix_captures_created_at", "created_at"),
        Index("ix_captures_task_id", "task_id"),
    )
