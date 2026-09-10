"""Организации-партнёры проекта

Связь, а не список в поле проекта: у одного проекта партнёров несколько, и у каждого своя
роль. Строкой их хранить нельзя — потеряется ответ на вопрос «с какими организациями мы
работаем», ради которого справочник организаций и заводился (ТЗ 6.1, сценарий U6).

Удаление организации, пока связь существует, запрещено (RESTRICT), а не каскадом:
организация уходит из справочника, а история, с кем шёл проект, остаётся.

Ревизия: 0009_project_partners
Предыдущая: 0008_milestones
Создана: 2026-09-10 18:01:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_project_partners"
down_revision: str | None = "0008_milestones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_partners",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_project_partners_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_partners_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_partners")),
        sa.UniqueConstraint(
            "project_id",
            "organization_id",
            name=op.f("uq_project_partners_project_id_organization_id"),
        ),
    )
    op.create_index(
        "ix_project_partners_organization_id", "project_partners", ["organization_id"], unique=False
    )


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_index("ix_project_partners_organization_id", table_name="project_partners")
    op.drop_table("project_partners")
