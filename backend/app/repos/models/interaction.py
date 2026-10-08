"""Письма и соглашения — раздел «Взаимодействие» (ТЗ 3.4).

Экран утверждён заказчиком 01.10.2026; таблицы — под него (миграция `0006_interaction`).

**Письмо** вносится, только если нужен ответ или действие руководителя либо стоит срок
(ТЗ 3.4): это не почтовый архив, а очередь «кто кого ждёт». Состояние письма — ждём ответа,
должны ответить, отвечено — считается по направлению и дате ответа и не хранится
(инвариант 1).

**Соглашение** движется правкой следующего шага или его даты (V40): момент последнего
движения — `moved_at`, от него считается «спит».

Связь письма с подготовкой доклада (ТЗ 3.4) появится вместе с разделом «Доклады и
мероприятия»: поле без таблицы, на которую оно ссылается, — поле «на будущее»
(инвариант 14). Вложения писем — с разделом «Файлы».
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.interaction import (
    NUMBER_MAX_LENGTH,
    SUBJECT_MAX_LENGTH,
    AgreementKind,
    Direction,
    Rating,
)
from app.repos.base import Base, Timestamps, UUIDPrimaryKey, Versioned
from app.repos.models.audit import Auditable


def _values(enum: type[Direction | Rating | AgreementKind]) -> str:
    return ", ".join(f"'{item.value}'" for item in enum)


class Letter(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Письмо: направление, организация, тема, номер и дата, срок ответа, ответ, оценка."""

    __tablename__ = "letters"

    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    """Не CASCADE: удаление организации не должно уносить переписку с ней."""

    subject: Mapped[str] = mapped_column(String(SUBJECT_MAX_LENGTH), nullable=False)
    number: Mapped[str | None] = mapped_column(String(NUMBER_MAX_LENGTH), nullable=True)
    sent_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    """Срок ответа: у входящего — наш, у исходящего — попрошенный у них (V39)."""

    author_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    ijro_assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ijro_assignments.id", ondelete="SET NULL"), nullable=True
    )
    answered_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    reply_number: Mapped[str | None] = mapped_column(String(NUMBER_MAX_LENGTH), nullable=True)
    """Номер ответного письма — чтобы найти его в канцелярии, а не в системе."""

    rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    """Оценка полученного ответа руководителем (V38); кто и когда — в журнале."""

    __table_args__ = (
        CheckConstraint(f"direction IN ({_values(Direction)})", name="direction_is_known"),
        CheckConstraint(f"rating IS NULL OR rating IN ({_values(Rating)})", name="rating_is_known"),
        # Оценивается только полученный ответ на наше письмо — правило держит и база.
        CheckConstraint(
            "rating IS NULL OR (direction = 'outgoing' AND answered_on IS NOT NULL)",
            name="rating_only_for_received_reply",
        ),
        CheckConstraint(
            "answered_on IS NULL OR answered_on >= sent_on", name="answer_not_before_letter"
        ),
        CheckConstraint(
            "project_id IS NULL OR ijro_assignment_id IS NULL", name="one_link_at_most"
        ),
        # «Кто нам не отвечает» и карточка организации — по организации среди неотвеченных.
        Index("ix_letters_organization_id_answered_on", "organization_id", "answered_on"),
    )


class Agreement(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Соглашение: меморандум или договор, следующий шаг и его дата, ответственный."""

    __tablename__ = "agreements"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(SUBJECT_MAX_LENGTH), nullable=False)
    signed_on: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_step_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsible_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    moved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    """Последнее движение — правка следующего шага или его даты (V40)."""

    __table_args__ = (
        CheckConstraint(f"kind IN ({_values(AgreementKind)})", name="kind_is_known"),
        Index("ix_agreements_organization_id", "organization_id"),
    )
