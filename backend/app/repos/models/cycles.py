"""Годовые циклы (ТЗ 3.1).

Хранится правило, а не даты: «ежегодно в феврале» — одна строка, а не четыре записи в год,
которые помощник заводит руками и однажды забывает завести. Даты система разворачивает
сама на год вперёд (`app.domain.cycles`) и в базу не пишет — иначе перенос правила оставил
бы после себя старые даты, и календарь показывал бы оба варианта сразу.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.cycles import CycleRule
from app.repos.base import Base, Timestamps, UUIDPrimaryKey, Versioned
from app.repos.models.audit import Auditable

RULES = ", ".join(f"'{rule.value}'" for rule in CycleRule)


class YearlyCycle(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Повторяющийся срок, который система разворачивает в конкретные даты."""

    __tablename__ = "yearly_cycles"

    title: Mapped[str] = mapped_column(String(300), nullable=False)

    rule: Mapped[str] = mapped_column(String(20), nullable=False)
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    day: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    every_years: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    anchor_year: Mapped[int] = mapped_column(Integer, nullable=False)
    """Год, от которого отсчитывается «раз в N лет».

    Без него цикл не знает, какие именно три года имеются в виду, и ответ зависел бы от
    того, когда его спросили.
    """

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    responsible_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    """Цикл отменяют, а не удаляют: он мог породить работу, о которой ещё помнят."""

    __table_args__ = (
        CheckConstraint(f"rule IN ({RULES})", name="rule_is_known"),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_is_a_month"),
        CheckConstraint("day BETWEEN 1 AND 31", name="day_is_a_day"),
        CheckConstraint("every_years BETWEEN 1 AND 10", name="every_years_is_sane"),
        Index("ix_yearly_cycles_project_id", "project_id"),
    )
