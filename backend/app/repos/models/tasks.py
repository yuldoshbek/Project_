"""Задачи (ТЗ 3.2).

Задача существует и вне проекта: половина работы аппарата — дела, у которых проекта нет и
не будет. Требовать проект означало бы заводить проекты-пустышки ради возможности
записать дело, и портфель перестал бы что-либо показывать.

**Четыре привязки, и любая из них необязательна** (ТЗ 3.2): проект, поручение «Ижро»,
письмо, подготовка доклада или мероприятия. Отдельными столбцами, а не парой
«тип объекта + идентификатор»: у каждой привязки свой внешний ключ, и база сама не даёт
сослаться в пустоту. Полиморфная ссылка этого не умеет — ею уже оплачено то, что
комментарии приходится убирать руками при удалении владельца.

Столбцы письма и подготовки появятся вместе со своими таблицами в блоке 2: заводить
внешний ключ на таблицу, которой нет, нельзя, а заводить столбец без ключа — значит
завести поле «на будущее» (инвариант 14).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey, Versioned
from app.repos.models.audit import Auditable


class Task(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Конкретное действие одного ответственного к сроку."""

    __tablename__ = "tasks"

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    task_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_types.id"), nullable=True
    )
    """Тип задачи из одиннадцати (ТЗ 3.9).

    Необязателен: обязательное поле у задачи одно — название (ТЗ 7). Создание строкой
    разбирает тип из текста и подставляет его, но не требует.
    """

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    ijro_assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ijro_assignments.id", ondelete="SET NULL"), nullable=True
    )
    """Поручение, из которого задача выросла («разложить на задачу», ТЗ 2).

    `SET NULL`, а не `CASCADE`: поручение снимают с контроля, а наша работа по нему
    остаётся — и остаётся ответом на вопрос, что мы успели сделать.
    """

    assignee_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20), ForeignKey("task_statuses.code"), nullable=False
    )

    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    original_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """Первый срок. Ведётся системой: появляется вместе с первым назначенным сроком."""

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """Отметки времени ставит система, а не человек: спрашивать у помощника, когда именно
    работа пошла, — лишний ввод, а незаполненное поле делает бесполезной всю статистику."""

    __table_args__ = (
        # Лестница внимания и списки читают задачи по сроку внутри статуса.
        Index("ix_tasks_status_due_at", "status", "due_at"),
        Index("ix_tasks_assignee_person_id_status", "assignee_person_id", "status"),
        Index("ix_tasks_project_id_status", "project_id", "status"),
        Index("ix_tasks_ijro_assignment_id", "ijro_assignment_id"),
    )
