"""Комментарии и уведомления

Одна таблица комментариев на проекты и задачи, а не две: реплика устроена одинаково,
различается только то, к чему она относится. Ссылка внешним ключом не выражается —
`entity_id` указывает то на одну таблицу, то на другую, — поэтому целостность держит
сервис, а не база, и это записано там же, где живёт удаление.

Удаление мягкое: `deleted_at`. Реплика остаётся строкой, но в ленту приходит без текста.
Пропуск в переписке делает соседние реплики непонятными — читатель не может отличить
«здесь ничего не было» от «здесь было и убрали».

`notifications` заведена по минимуму: только то, без чего упоминание в комментарии не
работает. Каналы, расписание и отметка о прочтении появятся с центром уведомлений
(ORB-037) и рассылкой (ORB-035, ORB-040) — своими миграциями. Класть их сейчас значило бы
завести шесть полей, которые полгода будут пустыми, а потом гадать, что каждое значило.

`dedup_key` уникален: правка реплики, в которой то же имя осталось на месте, упирается в
уникальность и второго уведомления не порождает (инвариант 6).

Ревизия: 0012_comments_and_notifications
Предыдущая: 0011_checklists_and_tags
Создана: 2026-09-12 10:55:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_comments_and_notifications"
down_revision: str | None = "0011_checklists_and_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "entity_type IN ('project', 'task')", name=op.f("ck_comments_entity_type_is_known")
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_comments_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
    )
    op.create_index(
        "ix_comments_entity_type_entity_id_created_at",
        "comments",
        ["entity_type", "entity_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "notifications",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("dedup_key", sa.String(length=200), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("dedup_key", name=op.f("uq_notifications_dedup_key")),
    )
    op.create_index(
        "ix_notifications_user_id_created_at",
        "notifications",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_index("ix_notifications_user_id_created_at", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_comments_entity_type_entity_id_created_at", table_name="comments")
    op.drop_table("comments")
