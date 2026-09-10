"""Задачи.

Задача существует и вне проекта (ТЗ 1): половина работы аппарата — поручения, у которых
проекта нет и не будет. Требовать проект означало бы заводить проекты-пустышки ради
возможности записать поручение, и портфель перестал бы что-либо показывать.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey
from app.repos.models.audit import Auditable


class Task(Auditable, UUIDPrimaryKey, Timestamps, Base):
    """Задача или поручение (ТЗ 6.2)."""

    __tablename__ = "tasks"

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Исполнитель — сотрудник агентства, а не пользователь системы (ADR-0011): в ORBITA
    # он не входит. Пользователей двое, а исполнителей десятки.
    assignee_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20), ForeignKey("task_statuses.code"), nullable=False
    )
    priority_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("priorities.code"), nullable=False
    )

    # Срок — момент, а не дата: «до конца дня» и «к десяти утра» — разные обещания, и
    # напоминание за час до срока без времени не построить.
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Поручение руководителя, требующее контроля. Ход его исполнения после запуска
    # обмена будет принадлежать SETA (ADR-0015), но запрет на изменение статуса вводит
    # ORB-076 — вместе с самим обменом. Ввести его раньше значит сделать поручения
    # незакрываемыми: закрывать их станет некому, обмена-то ещё нет.
    is_control: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        # Просрочка: срок среди незакрытых. Индекс назван в критерии приёмки ORB-014 и
        # подтверждается планом запроса, а не верой.
        Index("ix_tasks_status_due_at", "status", "due_at"),
        # «Что на мне» — второй по частоте вопрос после «что горит».
        Index("ix_tasks_assignee_person_id_status", "assignee_person_id", "status"),
        # Задачи проекта и сигнал «есть просроченные» по проекту (ORB-074) без обхода
        # всех задач: один индекс отвечает на оба вопроса.
        Index("ix_tasks_project_id_status_due_at", "project_id", "status", "due_at"),
    )
