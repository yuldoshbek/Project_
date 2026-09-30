"""Записи Захвата

Таблица `captures` — запись одной кнопкой (ТЗ 7): экран Захвата утверждён заказчиком
28.09.2026, и таблица заводится под него (CLAUDE.md, цикл блока «экран → API»). Смысл
столбцов — в модели `app.repos.models.captures`.

Вторая миграция, а не правка первой: первая уже накатана на базы разработки и превью, и
добавить таблицу поверх дешевле, чем пересобирать их. Первая сводилась в одну, чтобы не
воспроизводить при каждом накате снесённую схему, — здесь сносить нечего.

Ревизия: 0002_captures
Предыдущая: 0001_foundation
Создана: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_captures"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "captures",
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('task', 'request', 'idea', 'letter', 'event')",
            name=op.f("ck_captures_kind_is_known"),
        ),
        sa.CheckConstraint(
            "task_id IS NULL OR kind IN ('task', 'request')",
            name=op.f("ck_captures_only_work_has_task"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_captures_author_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_captures_task_id_tasks"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_captures")),
    )
    op.create_index("ix_captures_created_at", "captures", ["created_at"], unique=False)
    op.create_index("ix_captures_task_id", "captures", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_captures_task_id", table_name="captures")
    op.drop_index("ix_captures_created_at", table_name="captures")
    op.drop_table("captures")
