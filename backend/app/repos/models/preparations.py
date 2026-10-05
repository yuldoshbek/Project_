"""Подготовка докладов и мероприятий (ТЗ 3.5).

Подготовка — общая основа доклада и мероприятия: вид, название, дата показа, дата «начать
готовить», ответственный, этап, связь с проектом; у доклада — адресат. Чек-лист и запросы
сведений — свои таблицы: у каждого пункта и запроса свой автор, своя дата и своя версия.

Состояние запроса — запрошено, получено, просрочено — считается по сроку и дате получения и
не хранится (инвариант 1). Версии презентаций и замечания на слайд приходят вместе с
разделом «Файлы»: версия без файла — поле «на будущее» (инвариант 14).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import false

from app.domain.preparations import (
    TEXT_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    Addressee,
    PreparationKind,
    PrepStage,
)
from app.repos.base import Base, Timestamps, UUIDPrimaryKey, Versioned
from app.repos.models.audit import Auditable


def _values(enum: type[PreparationKind | PrepStage | Addressee]) -> str:
    return ", ".join(f"'{item.value}'" for item in enum)


class Preparation(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "preparations"

    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    addressee: Mapped[str | None] = mapped_column(String(20), nullable=True)
    show_on: Mapped[date] = mapped_column(Date, nullable=False)
    start_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsible_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    stage: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PrepStage.THESES.value, server_default="theses"
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(f"kind IN ({_values(PreparationKind)})", name="kind_is_known"),
        CheckConstraint(f"stage IN ({_values(PrepStage)})", name="stage_is_known"),
        CheckConstraint(
            f"addressee IS NULL OR addressee IN ({_values(Addressee)})",
            name="addressee_is_known",
        ),
        # Адресат — только у доклада: у мероприятия его нет (ТЗ 3.5).
        CheckConstraint("addressee IS NULL OR kind = 'report'", name="addressee_only_for_report"),
        CheckConstraint("start_on IS NULL OR start_on <= show_on", name="start_before_show"),
        Index("ix_preparations_show_on", "show_on"),
    )


class PreparationItem(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Пункт чек-листа подготовки; отметка — движение подготовки (V41)."""

    __tablename__ = "preparation_items"

    preparation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("preparations.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(TEXT_MAX_LENGTH), nullable=False)
    is_done: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_preparation_items_preparation_id", "preparation_id"),)


class InfoRequest(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Запрос сведений: что нужно, от кого — сотрудника или организации, срок, получено."""

    __tablename__ = "info_requests"

    preparation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("preparations.id", ondelete="CASCADE"), nullable=False
    )
    what: Mapped[str] = mapped_column(String(TEXT_MAX_LENGTH), nullable=False)
    source_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="RESTRICT"), nullable=True
    )
    source_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        # От кого — ровно один: сотрудник или организация (ТЗ 3.5).
        CheckConstraint(
            "(source_person_id IS NULL) <> (source_organization_id IS NULL)",
            name="exactly_one_source",
        ),
        Index("ix_info_requests_preparation_id", "preparation_id"),
    )
