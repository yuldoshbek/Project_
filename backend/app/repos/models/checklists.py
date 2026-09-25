"""Чек-лист задачи (ТЗ 3.2).

Строками, а не текстовым полем: список подзадач в тексте не даёт отметить пункт, а
отметка — это и есть признак жизни задачи, из которого собирается сигнал «молчит».

Прогресс здесь не хранится: он считается из самих пунктов (`app.domain.checklists`) по
той же причине, по которой не хранится просрочка (инвариант 1).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey, Versioned
from app.repos.models.audit import Auditable


class TaskChecklistItem(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Пункт чек-листа.

    Журналируется наравне с задачей: «кто отметил пункт выполненным» — тот же вопрос, что
    «кто поменял статус», и по поручению он задаётся всерьёз.
    """

    __tablename__ = "task_checklist_items"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_task_checklist_items_task_id_sort_order", "task_id", "sort_order"),)
