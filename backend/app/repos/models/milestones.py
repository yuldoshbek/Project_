"""Вехи проекта (ТЗ 3.1).

Хранятся признак «пройдена» и дата прохождения; «пропущена» вычисляется на выдаче
(`app.domain.milestones`). Ограничение уровня строки закрепляет это в базе: веха не
бывает пройденной без даты прохождения и с датой, но не пройденной, — иначе первый же
привоз данных запишет туда состояние, которого расчёт не ожидает.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey, Versioned
from app.repos.models.audit import Auditable


class Milestone(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Шаг проекта с собственным сроком: разработка, согласование, внесение в Кабмин."""

    __tablename__ = "milestones"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    original_due_on: Mapped[date] = mapped_column(Date, nullable=False)
    """Первый срок вехи. Проставляется при создании и больше не меняется (ТЗ 3.1).

    По нему отвечают на вопрос «где продлевают хронически»: веха, которую двигали трижды,
    видна сразу, а по журналу изменений её пришлось бы искать.
    """

    is_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    passed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    """Когда веху прошли. Отвечает на вопрос «успели ли», в отличие от «сделали ли»."""

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """Порядок задаёт человек, а не дата: согласование идёт раньше подписания, даже если
    сроки у них совпали."""

    __table_args__ = (
        CheckConstraint(
            "(is_passed AND passed_on IS NOT NULL) OR (NOT is_passed AND passed_on IS NULL)",
            name="passed_milestone_has_a_date",
        ),
        Index("ix_milestones_project_id_sort_order", "project_id", "sort_order"),
        # Календарь и лестница внимания читают вехи по сроку среди непройденных.
        Index("ix_milestones_due_on", "due_on", postgresql_where="NOT is_passed"),
    )
