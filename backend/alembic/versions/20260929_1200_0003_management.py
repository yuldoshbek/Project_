"""Управление: версии справочников и порогов, действия обхода

Экран «Управление» утверждён заказчиком 29.09.2026, и схема меняется под него (CLAUDE.md,
цикл блока «экран → API»):

- **Версия** (инвариант 15) у значений справочников, вех шаблонов, организаций и порогов:
  их теперь правит помощник, и правка по устаревшей картине должна получать честный отказ,
  а не молча перезаписывать соседа. Уже заведённые строки получают версию 1.
- **`round_actions`** — действия обхода для «сделано на неделе» (допущение V20): только
  момент действия, почему — в модели `app.repos.models.round`.

Ревизия: 0003_management
Предыдущая: 0002_captures
Создана: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_management"
down_revision: str | None = "0002_captures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERSIONED = (
    "directions",
    "regions",
    "project_types",
    "task_types",
    "project_statuses",
    "task_statuses",
    "project_type_milestones",
    "organizations",
    "settings",
)


def upgrade() -> None:
    for table in VERSIONED:
        op.add_column(
            table,
            sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        )

    op.create_table(
        "round_actions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_round_actions")),
    )
    op.create_index("ix_round_actions_created_at", "round_actions", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_round_actions_created_at", table_name="round_actions")
    op.drop_table("round_actions")
    for table in reversed(VERSIONED):
        op.drop_column(table, "version")
