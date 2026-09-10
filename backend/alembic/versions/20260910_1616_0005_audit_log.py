"""Журнал изменений

Таблица только на дозапись. Неизменяемость обеспечивает база, а не приложение: журнал,
который может подчистить тот же код, что в него пишет, ничего не доказывает
([ADR-0010](../../../docs/adr/ADR-0010-audit-log.md)).

Защита сделана триггером, а не одним отзывом прав. Приложение подключается владельцем
таблицы, а владельцу права можно вернуть себе обратно — отзыв остановил бы стороннюю
роль, но не то приложение, от чьей ошибки журнал и защищают. Отзыв всё равно оставлен:
он закрывает будущие роли только на чтение, заводить которые придётся при первой же
проверке службы безопасности.

Ревизия: 0005_audit_log
Предыдущая: 0004_refresh_tokens
Создана: 2026-09-10 16:16:07.984355
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_audit_log"
down_revision: str | None = "0004_refresh_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Журнал изменений неизменяем: операция % запрещена', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;
"""


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_kind", sa.String(length=20), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_log_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(
        "ix_audit_log_entity_type_entity_id_occurred_at",
        "audit_log",
        ["entity_type", "entity_id", "occurred_at"],
        unique=False,
    )
    op.create_index("ix_audit_log_occurred_at", "audit_log", ["occurred_at"], unique=False)

    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(
        "CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()"
    )
    # TRUNCATE обходит построчные триггеры — без этой строки журнал стирается одной
    # командой, и все три предыдущие защиты оказываются декорацией.
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only()"
    )
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM PUBLIC")


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_append_only()")
    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
    op.drop_index("ix_audit_log_entity_type_entity_id_occurred_at", table_name="audit_log")
    op.drop_table("audit_log")
