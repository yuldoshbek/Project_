"""Проекты.

Ссылки на справочники идут по `code`, а не по идентификатору: код известен коду
(`app.domain.dictionaries`), и запрос «все приостановленные» читается без соединения с
таблицей статусов. Переименование статуса при этом ничего не ломает — меняется название,
не код.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.projects import MAX_PROGRESS, MIN_PROGRESS, Classification, ProgressMode
from app.repos.base import Base, Timestamps, UUIDPrimaryKey
from app.repos.models.audit import Auditable


class Project(Auditable, UUIDPrimaryKey, Timestamps, Base):
    """Проект или мини-проект агентства (ТЗ 6.1)."""

    __tablename__ = "projects"

    # Человекочитаемый номер вида PRJ-2026-001. По нему проект называют вслух и ищут в
    # переписке; идентификатор для этого не годится.
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    classification: Mapped[str] = mapped_column(
        String(20), nullable=False, default=Classification.INTERNAL.value
    )

    direction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("directions.id"), nullable=False
    )
    # Куратор — сотрудник агентства, а не пользователь системы: пользователей двое, а
    # кураторов десятки (`app.domain.people`).
    curator_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )

    status_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("project_statuses.code"), nullable=False
    )
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("priorities.code"), nullable=False
    )

    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    finished_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    progress_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    progress_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default=ProgressMode.AUTO.value
    )

    # Справочно, без интеграции с финансовыми системами: ТЗ 2.5 прямо выносит бюджетный
    # и бухгалтерский учёт за границы системы.
    budget_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    @property
    def audit_is_classified(self) -> bool:
        """Содержимое закрытого проекта в журнал не выдаётся (ADR-0007, ORB-009).

        Факт изменения при этом остаётся: иначе закрытый проект можно менять бесследно —
        ровно та дыра, от которой журнал должен защищать.
        """
        return self.classification == Classification.RESTRICTED

    __table_args__ = (
        CheckConstraint(
            f"progress_pct BETWEEN {MIN_PROGRESS} AND {MAX_PROGRESS}",
            name="progress_pct_is_a_percentage",
        ),
        # Срок раньше начала — не опечатка, а неверные данные: по ним считается светофор
        # и доля пройденного времени. Проверка стоит и в домене, и здесь: домен ловит
        # ошибку с понятным текстом, база — обход домена миграцией данных или SQL.
        CheckConstraint("due_on >= started_on", name="due_on_is_not_before_started_on"),
        # Причина обязательна там, где статус её требует. Список кодов в ограничении, а
        # не соединение со справочником: проверки уровня строки не читают другие таблицы.
        CheckConstraint(
            "status_code NOT IN ('on_hold', 'cancelled') "
            "OR (status_reason IS NOT NULL AND btrim(status_reason) <> '')",
            name="paused_and_cancelled_need_a_reason",
        ),
        # Основной список: портфель по направлению со свежими сроками впереди.
        Index("ix_projects_direction_id_due_on", "direction_id", "due_on"),
        # Просрочка и светофор считаются по сроку среди незакрытых.
        Index("ix_projects_status_code_due_on", "status_code", "due_on"),
    )
