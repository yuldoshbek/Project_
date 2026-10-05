"""Подготовка докладов и мероприятий

Раздел «Доклады и мероприятия» (ТЗ 3.5, блок 2):

- **`preparations`** — доклад или мероприятие: дата показа, «начать готовить», ответственный,
  этап, адресат доклада, связь с проектом;
- **`preparation_items`** — чек-лист подготовки;
- **`info_requests`** — запросы сведений: что нужно, от кого (сотрудник или организация —
  ровно один), срок, дата получения;
- **решение и вопрос по подготовке** — `target_type` пополняется `preparation`: подготовка
  встаёт строкой Пульта, и кнопки у строки те же.

Откат удаляет таблицы и решения и вопросы по подготовкам.

Ревизия: 0007_preparations
Предыдущая: 0006_interaction
Создана: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_preparations"
down_revision: str | None = "0006_interaction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TARGETS = "'project', 'task', 'milestone', 'ijro_assignment', 'letter', 'agreement', 'preparation'"
OLD_TARGETS = "'project', 'task', 'milestone', 'ijro_assignment', 'letter', 'agreement'"
ADDRESSEES = "'cabinet', 'administration', 'president', 'prime_minister', 'other'"


def _targets(values: str) -> None:
    for table in ("leader_decisions", "leader_questions"):
        name = op.f(f"ck_{table}_target_type_is_known")
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"target_type IN ({values})")


def upgrade() -> None:
    op.create_table(
        "preparations",
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("addressee", sa.String(length=20), nullable=True),
        sa.Column("show_on", sa.Date(), nullable=False),
        sa.Column("start_on", sa.Date(), nullable=True),
        sa.Column("responsible_person_id", sa.UUID(), nullable=True),
        sa.Column("stage", sa.String(length=20), server_default="theses", nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"addressee IS NULL OR addressee IN ({ADDRESSEES})",
            name=op.f("ck_preparations_addressee_is_known"),
        ),
        sa.CheckConstraint(
            "addressee IS NULL OR kind = 'report'",
            name=op.f("ck_preparations_addressee_only_for_report"),
        ),
        sa.CheckConstraint(
            "kind IN ('report', 'event')", name=op.f("ck_preparations_kind_is_known")
        ),
        sa.CheckConstraint(
            "stage IN ('theses', 'data', 'draft', 'approval', 'rehearsal', 'shown')",
            name=op.f("ck_preparations_stage_is_known"),
        ),
        sa.CheckConstraint(
            "start_on IS NULL OR start_on <= show_on",
            name=op.f("ck_preparations_start_before_show"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_preparations_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["responsible_person_id"],
            ["people.id"],
            name=op.f("fk_preparations_responsible_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_preparations")),
    )
    op.create_index("ix_preparations_show_on", "preparations", ["show_on"], unique=False)
    op.create_table(
        "info_requests",
        sa.Column("preparation_id", sa.UUID(), nullable=False),
        sa.Column("what", sa.String(length=1000), nullable=False),
        sa.Column("source_person_id", sa.UUID(), nullable=True),
        sa.Column("source_organization_id", sa.UUID(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("received_on", sa.Date(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(source_person_id IS NULL) <> (source_organization_id IS NULL)",
            name=op.f("ck_info_requests_exactly_one_source"),
        ),
        sa.ForeignKeyConstraint(
            ["preparation_id"],
            ["preparations.id"],
            name=op.f("fk_info_requests_preparation_id_preparations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_organization_id"],
            ["organizations.id"],
            name=op.f("fk_info_requests_source_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_person_id"],
            ["people.id"],
            name=op.f("fk_info_requests_source_person_id_people"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_info_requests")),
    )
    op.create_index(
        "ix_info_requests_preparation_id", "info_requests", ["preparation_id"], unique=False
    )
    op.create_table(
        "preparation_items",
        sa.Column("preparation_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("is_done", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["preparation_id"],
            ["preparations.id"],
            name=op.f("fk_preparation_items_preparation_id_preparations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_preparation_items")),
    )
    op.create_index(
        "ix_preparation_items_preparation_id", "preparation_items", ["preparation_id"], unique=False
    )
    _targets(TARGETS)


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.execute("DELETE FROM leader_questions WHERE target_type = 'preparation'")
    op.execute("DELETE FROM leader_decisions WHERE target_type = 'preparation'")
    _targets(OLD_TARGETS)
    op.drop_index("ix_preparation_items_preparation_id", table_name="preparation_items")
    op.drop_table("preparation_items")
    op.drop_index("ix_info_requests_preparation_id", table_name="info_requests")
    op.drop_table("info_requests")
    op.drop_index("ix_preparations_show_on", table_name="preparations")
    op.drop_table("preparations")
