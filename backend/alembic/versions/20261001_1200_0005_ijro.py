"""Ижро: этапы ТЗ 3.3, точность «месяц», история продлений и контрольные отметки

Экран «Ижро» утверждён заказчиком 30.09.2026, и схема блока 0 расходится с ним в трёх
местах (CLAUDE.md, цикл блока «экран → API»):

- **Этапы** — пять этапов ТЗ 3.3 (допущение V32): «вернули на доработку» появляется,
  «зависит от головного» уходит в ступень лестницы, «исполнено» сливается со «снято с
  контроля». Уже записанные строки переводятся: `blocked_by_lead` → `in_progress` (работа
  идёт, ждём чужих — это ступень), `done` → `removed_from_control`.
- **Точность срока «месяц»** (допущение V33): срок «до конца месяца» не горит, как и «до
  конца года».
- **История продлений и контрольные отметки** — `ijro_extensions`, `ijro_control_marks`;
  у поручения — исходный срок и «запрошено продление», у партии привоза — дата таблицы.

Откат возвращает прежние наборы: `returned` → `in_progress`, `month` → `exact`; история
продлений и отметки удаляются вместе с таблицами.

Ревизия: 0005_ijro
Предыдущая: 0004_push
Создана: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_ijro"
down_revision: str | None = "0004_push"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATES = "'not_started', 'in_progress', 'submitted', 'returned', 'removed_from_control'"
OLD_STATES = (
    "'not_started', 'in_progress', 'blocked_by_lead', 'submitted', 'done', 'removed_from_control'"
)
PRECISIONS = "'exact', 'month', 'end_of_year'"
OLD_PRECISIONS = "'exact', 'end_of_year'"


def _replace_check(name: str, condition: str) -> None:
    op.drop_constraint(op.f(f"ck_ijro_assignments_{name}"), "ijro_assignments", type_="check")
    op.create_check_constraint(op.f(f"ck_ijro_assignments_{name}"), "ijro_assignments", condition)


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_ijro_assignments_state_is_known"), "ijro_assignments", type_="check"
    )
    op.execute("UPDATE ijro_assignments SET state = 'in_progress' WHERE state = 'blocked_by_lead'")
    op.execute("UPDATE ijro_assignments SET state = 'removed_from_control' WHERE state = 'done'")
    op.create_check_constraint(
        op.f("ck_ijro_assignments_state_is_known"), "ijro_assignments", f"state IN ({STATES})"
    )
    _replace_check("due_precision_is_known", f"due_precision IN ({PRECISIONS})")

    op.add_column("ijro_assignments", sa.Column("original_due_on", sa.Date(), nullable=True))
    op.add_column(
        "ijro_assignments",
        sa.Column("extension_requested", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    # Исходный срок у уже записанных строк — нынешний: переносов до этой миграции система
    # не помнила, и выдумывать их нечем.
    op.execute("UPDATE ijro_assignments SET original_due_on = due_on")
    op.add_column("ijro_imports", sa.Column("table_on", sa.Date(), nullable=True))

    op.create_table(
        "ijro_extensions",
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("due_from", sa.Date(), nullable=False),
        sa.Column("due_to", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("import_batch_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('extension', 'correction')", name=op.f("ck_ijro_extensions_kind_is_known")
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["ijro_assignments.id"],
            name=op.f("fk_ijro_extensions_assignment_id_ijro_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["ijro_imports.id"],
            name=op.f("fk_ijro_extensions_import_batch_id_ijro_imports"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ijro_extensions")),
    )
    op.create_index(
        "ix_ijro_extensions_assignment_id_created_at",
        "ijro_extensions",
        ["assignment_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "ijro_control_marks",
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("promised_on", sa.Date(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('contacted', 'doing', 'no_answer')",
            name=op.f("ck_ijro_control_marks_kind_is_known"),
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["ijro_assignments.id"],
            name=op.f("fk_ijro_control_marks_assignment_id_ijro_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_ijro_control_marks_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ijro_control_marks")),
    )
    op.create_index(
        "ix_ijro_control_marks_assignment_id_created_at",
        "ijro_control_marks",
        ["assignment_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ijro_control_marks_assignment_id_created_at", table_name="ijro_control_marks")
    op.drop_table("ijro_control_marks")
    op.drop_index("ix_ijro_extensions_assignment_id_created_at", table_name="ijro_extensions")
    op.drop_table("ijro_extensions")

    op.drop_column("ijro_imports", "table_on")
    op.drop_column("ijro_assignments", "extension_requested")
    op.drop_column("ijro_assignments", "original_due_on")

    op.drop_constraint(
        op.f("ck_ijro_assignments_due_precision_is_known"), "ijro_assignments", type_="check"
    )
    op.execute("UPDATE ijro_assignments SET due_precision = 'exact' WHERE due_precision = 'month'")
    op.create_check_constraint(
        op.f("ck_ijro_assignments_due_precision_is_known"),
        "ijro_assignments",
        f"due_precision IN ({OLD_PRECISIONS})",
    )
    op.drop_constraint(
        op.f("ck_ijro_assignments_state_is_known"), "ijro_assignments", type_="check"
    )
    op.execute("UPDATE ijro_assignments SET state = 'in_progress' WHERE state = 'returned'")
    op.create_check_constraint(
        op.f("ck_ijro_assignments_state_is_known"),
        "ijro_assignments",
        f"state IN ({OLD_STATES})",
    )
