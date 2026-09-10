"""Вехи проекта.

Хранятся два состояния из трёх: `missed` вычисляется на выдаче
(`app.domain.milestones`). Ограничение уровня строки закрепляет это в базе — иначе
первый же скрипт импорта запишет туда третье значение, и вычисление начнёт спорить с
хранимым.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.milestones import MilestoneState
from app.repos.base import Base, Timestamps, UUIDPrimaryKey
from app.repos.models.audit import Auditable

STATES = ", ".join(f"'{state.value}'" for state in MilestoneState)


class Milestone(Auditable, UUIDPrimaryKey, Timestamps, Base):
    """Контрольная точка проекта (ТЗ 6.1)."""

    __tablename__ = "milestones"

    # Веха без проекта не существует: она и есть отметка на его пути. Удаление проекта
    # уносит вехи с собой — оставлять их сиротами не для кого.
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=MilestoneState.PLANNED.value
    )

    # Порядок задаёт человек: вехи идут не по дате, а по смыслу — согласование раньше
    # подписания, даже если сроки поставили одинаковые.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint(f"state IN ({STATES})", name="state_is_planned_or_done"),
        Index("ix_milestones_project_id_sort_order", "project_id", "sort_order"),
        # Ближайшие вехи портфеля — для Гантта (ORB-031) и ленты календаря (ORB-026).
        Index("ix_milestones_due_on", "due_on"),
    )
