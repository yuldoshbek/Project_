"""Уведомления: подписки устройств и отметка доставки

Экран «Сводка» утверждён заказчиком 29.09.2026, и схема меняется под настоящую доставку
([ADR-0036](../../../docs/adr/ADR-0036-web-push.md)):

- **`notifications.sent_at`** — пуш принят службой хотя бы для одного устройства: по нему
  вкладка «Сводка» говорит помощнику «пришла в 08:30», а повторный прогон не шлёт второй;
- **`entity_type` и `entity_id` необязательны** — сводка о дне целиком, а не о записи;
- **`push_subscriptions`** — подписки браузеров; почему не журналируются и почему
  отключённая службой подписка остаётся с отметкой `gone_at` — в модели
  `app.repos.models.push`.

Откат удаляет уведомления без записи (сводки): прежняя схема требовала запись у каждого, и
вернуть её с такими строками нельзя. Сводка — след отправки, а не данные агентства.

Ревизия: 0004_push
Предыдущая: 0003_management
Создана: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_push"
down_revision: str | None = "0003_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column(
        "notifications", "entity_type", existing_type=sa.String(length=20), nullable=True
    )
    op.alter_column("notifications", "entity_id", existing_type=sa.UUID(), nullable=True)

    op.create_table(
        "push_subscriptions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("endpoint", sa.String(length=1000), nullable=False),
        sa.Column("p256dh", sa.String(length=100), nullable=False),
        sa.Column("auth", sa.String(length=50), nullable=False),
        sa.Column("device", sa.String(length=50), nullable=False),
        sa.Column("gone_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_push_subscriptions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscriptions")),
        sa.UniqueConstraint("endpoint", name=op.f("uq_push_subscriptions_endpoint")),
    )
    op.create_index(
        "ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")

    op.execute("DELETE FROM notifications WHERE entity_type IS NULL OR entity_id IS NULL")
    op.alter_column("notifications", "entity_id", existing_type=sa.UUID(), nullable=False)
    op.alter_column(
        "notifications", "entity_type", existing_type=sa.String(length=20), nullable=False
    )
    op.drop_column("notifications", "sent_at")
