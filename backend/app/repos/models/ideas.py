"""Идеи и карты (ТЗ 3.6).

Идея помнит, что из неё выросло: проект или задачу. Ссылка — `SET NULL`: запись о том, что
было предложено и решено, переживает отменённый проект. Узел карты ссылается на проект или
задачу так же — и в режиме «Структура» показывает их ступень Пульта.

Возраст идеи на рассмотрении — от `review_at` (V46): набросок ждёт помощника, руководителя
ждёт только отправленное.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.ideas import (
    MAP_TITLE_MAX_LENGTH,
    NODE_TEXT_MAX_LENGTH,
    IdeaStep,
    MapMode,
    Outcome,
)
from app.repos.base import Base, Timestamps, UUIDPrimaryKey, Versioned
from app.repos.models.audit import Auditable


def _values(enum: type[IdeaStep | Outcome | MapMode]) -> str:
    return ", ".join(f"'{item.value}'" for item in enum)


class Idea(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "ideas"

    text: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    """Кто записал: экран подписывает идею ролью автора (инвариант 13)."""

    step: Mapped[str] = mapped_column(
        String(10), nullable=False, default=IdeaStep.DRAFT.value, server_default="draft"
    )
    outcome: Mapped[str | None] = mapped_column(String(10), nullable=True)
    review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(f"step IN ({_values(IdeaStep)})", name="step_is_known"),
        CheckConstraint(
            f"outcome IS NULL OR outcome IN ({_values(Outcome)})", name="outcome_is_known"
        ),
        # Решение есть ровно у решённой идеи; ссылка — только у решения с тем же видом.
        CheckConstraint("(step = 'decided') = (outcome IS NOT NULL)", name="outcome_when_decided"),
        CheckConstraint(
            "project_id IS NULL OR outcome = 'project'", name="project_only_if_project"
        ),
        CheckConstraint("task_id IS NULL OR outcome = 'task'", name="task_only_if_task"),
        CheckConstraint("step <> 'review' OR review_at IS NOT NULL", name="review_has_moment"),
        Index("ix_ideas_step", "step"),
    )


class IdeaMap(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "idea_maps"

    title: Mapped[str] = mapped_column(String(MAP_TITLE_MAX_LENGTH), nullable=False)
    mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default=MapMode.SKETCH.value, server_default="sketch"
    )

    __table_args__ = (CheckConstraint(f"mode IN ({_values(MapMode)})", name="mode_is_known"),)


class MapNode(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Узел карты: подпись, место на полотне, родитель, связь с настоящей записью."""

    __tablename__ = "map_nodes"

    map_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("idea_maps.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("map_nodes.id", ondelete="CASCADE"), nullable=True
    )
    """Удаление узла уносит потомков (`app.domain.ideas.subtree`): ветка без корня — обрывок."""

    text: Mapped[str] = mapped_column(String(NODE_TEXT_MAX_LENGTH), nullable=False)
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("project_id IS NULL OR task_id IS NULL", name="one_link"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        Index("ix_map_nodes_map_id", "map_id"),
    )
