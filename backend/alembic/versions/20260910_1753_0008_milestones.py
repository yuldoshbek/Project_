"""Вехи проекта

Хранятся два состояния из трёх: `planned` и `done`. Третье, `missed`, вычисляется на
выдаче по наступившему сроку — по той же причине, по которой не хранится просрочка
задачи ([ADR-0004](../../../docs/adr/ADR-0004-overdue-is-computed.md)): хранимое значение
теряет исходное, а фоновое задание, переписывающее статусы по ночам, отстаёт на сутки.

Ограничение уровня строки закрепляет это в базе: без него первый же скрипт импорта
запишет туда третье значение, и вычисление начнёт спорить с хранимым.

Ревизия: 0008_milestones
Предыдущая: 0007_tasks
Создана: 2026-09-10 17:53:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_milestones"
down_revision: str | None = "0007_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "milestones",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('planned', 'done')", name=op.f("ck_milestones_state_is_planned_or_done")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_milestones_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestones")),
    )
    op.create_index("ix_milestones_due_on", "milestones", ["due_on"], unique=False)
    op.create_index(
        "ix_milestones_project_id_sort_order",
        "milestones",
        ["project_id", "sort_order"],
        unique=False,
    )


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_index("ix_milestones_project_id_sort_order", table_name="milestones")
    op.drop_index("ix_milestones_due_on", table_name="milestones")
    op.drop_table("milestones")
