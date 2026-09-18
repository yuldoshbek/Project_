"""Снять вход: таблица сессий и колонки паролей больше не нужны

Решение заказчика 18.09.2026 — «убери вход, авторизация не нужна, свободный доступ» — и
[ADR-0026](../../../docs/adr/ADR-0026-no-login-perimeter-auth.md). Пользователей двое,
границы между ними нет (ADR-0011), и экран входа охранял не их друг от друга, а систему от
внешнего мира. Эту работу забирает периметр: обратный прокси на сервере агентства.

**Что удаляется и почему это безопасно.** `refresh_tokens` хранила серверные токены
обновления: без них «выход» не существовал бы как действие. Выхода больше нет, входа тоже,
и таблица стала мёртвой. Колонки `password_hash`, `must_change_password`,
`failed_login_count`, `locked_until`, `last_login_at` обслуживали вход и ограничение
частоты попыток — им нечего обслуживать.

**Что остаётся и почему.** Таблица `users` с двумя строками из сидов **не удаляется**: у
записи в `audit_log` обязан быть автор (инвариант 4, ADR-0010), а решение руководителя
должно быть отличимо от заметки помощника. Роль приезжает заголовком `X-Orbita-Actor`, и
сервер верит ему на слово — заголовок подписывает действие, а не охраняет данные.

**Откат честный, но не полный.** Обратная миграция возвращает таблицу, индекс и колонки
пустыми: хеши паролей и живые сессии не восстанавливаются ниоткуда. Делать вид, что откат
возвращает прежнее состояние, было бы враньём — после него в системе нет ни одного пароля,
а команды, чтобы его назначить, ADR-0026 тоже снял.

Определения таблицы и индекса повторяют миграцию `0004` дословно, включая ссылку на саму
себя и имена ограничений. Иначе откат до `base` спотыкается о `DROP INDEX` из `0004`:
она удаляет то, чего мы не создали.

Ревизия: 0017_drop_login
Предыдущая: 0016_planned_due_at
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_drop_login"
down_revision = "0016_planned_due_at"
branch_labels = None
depends_on = None

LOGIN_COLUMNS = (
    "last_login_at",
    "locked_until",
    "failed_login_count",
    "must_change_password",
    "password_hash",
)


def upgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id_expires_at", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    for column in LOGIN_COLUMNS:
        op.drop_column("users", column)


def downgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("failed_login_count", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "refresh_tokens",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.UUID(), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_tokens.id"],
            name=op.f("fk_refresh_tokens_replaced_by_id_refresh_tokens"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(
        "ix_refresh_tokens_user_id_expires_at",
        "refresh_tokens",
        ["user_id", "expires_at"],
        unique=False,
    )
