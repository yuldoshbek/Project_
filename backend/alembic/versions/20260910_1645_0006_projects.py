"""Проекты

Ссылки на справочники идут по `code`, а не по идентификатору: код известен коду
(`app.domain.dictionaries`), и запрос «все приостановленные» читается без соединения со
справочником. Переименование статуса при этом ничего не ломает.

Три проверки уровня строки дублируют домен намеренно. Домен ловит ошибку с понятным
пользователю текстом; база ловит обход домена — миграцию данных, ручной SQL, будущий
импорт. Проверка, которая живёт только в приложении, защищает ровно до первого скрипта.

Ревизия: 0006_projects
Предыдущая: 0005_audit_log
Создана: 2026-09-10 16:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_projects"
down_revision: str | None = "0005_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("classification", sa.String(length=20), nullable=False),
        sa.Column("direction_id", sa.UUID(), nullable=False),
        sa.Column("curator_person_id", sa.UUID(), nullable=True),
        sa.Column("status_code", sa.String(length=50), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("priority_code", sa.String(length=50), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("finished_on", sa.Date(), nullable=True),
        sa.Column("progress_pct", sa.SmallInteger(), nullable=False),
        sa.Column("progress_mode", sa.String(length=10), nullable=False),
        sa.Column("budget_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status_code NOT IN ('on_hold', 'cancelled') "
            "OR (status_reason IS NOT NULL AND btrim(status_reason) <> '')",
            name=op.f("ck_projects_paused_and_cancelled_need_a_reason"),
        ),
        sa.CheckConstraint(
            "due_on >= started_on", name=op.f("ck_projects_due_on_is_not_before_started_on")
        ),
        sa.CheckConstraint(
            "progress_pct BETWEEN 0 AND 100", name=op.f("ck_projects_progress_pct_is_a_percentage")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_projects_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["curator_person_id"],
            ["people.id"],
            name=op.f("fk_projects_curator_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["direction_id"], ["directions.id"], name=op.f("fk_projects_direction_id_directions")
        ),
        sa.ForeignKeyConstraint(
            ["priority_code"],
            ["priorities.code"],
            name=op.f("fk_projects_priority_code_priorities"),
        ),
        sa.ForeignKeyConstraint(
            ["status_code"],
            ["project_statuses.code"],
            name=op.f("fk_projects_status_code_project_statuses"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("code", name=op.f("uq_projects_code")),
    )
    op.create_index(
        "ix_projects_direction_id_due_on", "projects", ["direction_id", "due_on"], unique=False
    )
    op.create_index(
        "ix_projects_status_code_due_on", "projects", ["status_code", "due_on"], unique=False
    )


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_index("ix_projects_status_code_due_on", table_name="projects")
    op.drop_index("ix_projects_direction_id_due_on", table_name="projects")
    op.drop_table("projects")
