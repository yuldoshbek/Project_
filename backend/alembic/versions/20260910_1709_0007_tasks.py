"""Задачи

Задача живёт и вне проекта: половина работы аппарата — поручения, у которых проекта нет
и не будет. Требовать проект означало бы заводить проекты-пустышки ради возможности
записать поручение, и портфель перестал бы что-либо показывать (ТЗ 1).

Просрочки среди столбцов нет и не будет: это вычисляемое состояние, а не статус
([ADR-0004](../../../docs/adr/ADR-0004-overdue-is-computed.md)). Под неё заведён индекс
`(status, due_at)` — критерий приёмки ORB-014 требует подтвердить его планом запроса.

Ревизия: 0007_tasks
Предыдущая: 0006_projects
Создана: 2026-09-10 17:09:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_tasks"
down_revision: str | None = "0006_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assignee_person_id", sa.UUID(), nullable=True),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority_code", sa.String(length=50), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_control", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assignee_person_id"],
            ["people.id"],
            name=op.f("fk_tasks_assignee_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_tasks_author_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["priority_code"], ["priorities.code"], name=op.f("fk_tasks_priority_code_priorities")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_tasks_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["status"], ["task_statuses.code"], name=op.f("fk_tasks_status_task_statuses")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
        sa.UniqueConstraint("code", name=op.f("uq_tasks_code")),
    )
    op.create_index(
        "ix_tasks_assignee_person_id_status",
        "tasks",
        ["assignee_person_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_tasks_project_id_status_due_at",
        "tasks",
        ["project_id", "status", "due_at"],
        unique=False,
    )
    op.create_index("ix_tasks_status_due_at", "tasks", ["status", "due_at"], unique=False)


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_index("ix_tasks_status_due_at", table_name="tasks")
    op.drop_index("ix_tasks_project_id_status_due_at", table_name="tasks")
    op.drop_index("ix_tasks_assignee_person_id_status", table_name="tasks")
    op.drop_table("tasks")
