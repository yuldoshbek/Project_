"""Идеи и карты

Раздел «Идеи и карты» (блок 3, ТЗ 3.6):

- **`ideas`** — идея, её шаг (набросок, на рассмотрении, решено), решение (проект, задача,
  отложено) и ссылка на то, что из неё выросло;
- **`idea_maps`** — карта и её режим (набросок, структура);
- **`map_nodes`** — узел: подпись, место на полотне, родитель, связь с проектом или задачей.

Ревизия: 0009_ideas
Предыдущая: 0008_files
Создана: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_ideas"
down_revision: str | None = "0008_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idea_maps",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("mode", sa.String(length=10), server_default="sketch", nullable=False),
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
            "mode IN ('sketch', 'structure')", name=op.f("ck_idea_maps_mode_is_known")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idea_maps")),
    )
    op.create_table(
        "ideas",
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("step", sa.String(length=10), server_default="draft", nullable=False),
        sa.Column("outcome", sa.String(length=10), nullable=True),
        sa.Column("review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("task_id", sa.UUID(), nullable=True),
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
            "(step = 'decided') = (outcome IS NOT NULL)", name=op.f("ck_ideas_outcome_when_decided")
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('project', 'task', 'postponed')",
            name=op.f("ck_ideas_outcome_is_known"),
        ),
        sa.CheckConstraint(
            "project_id IS NULL OR outcome = 'project'",
            name=op.f("ck_ideas_project_only_if_project"),
        ),
        sa.CheckConstraint(
            "step <> 'review' OR review_at IS NOT NULL", name=op.f("ck_ideas_review_has_moment")
        ),
        sa.CheckConstraint(
            "step IN ('draft', 'review', 'decided')", name=op.f("ck_ideas_step_is_known")
        ),
        sa.CheckConstraint(
            "task_id IS NULL OR outcome = 'task'", name=op.f("ck_ideas_task_only_if_task")
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name=op.f("fk_ideas_author_id_users")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_ideas_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_ideas_task_id_tasks"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ideas")),
    )
    op.create_index("ix_ideas_step", "ideas", ["step"], unique=False)
    op.create_table(
        "map_nodes",
        sa.Column("map_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("text", sa.String(length=300), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("task_id", sa.UUID(), nullable=True),
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
            "parent_id IS NULL OR parent_id <> id", name=op.f("ck_map_nodes_not_own_parent")
        ),
        sa.CheckConstraint(
            "project_id IS NULL OR task_id IS NULL", name=op.f("ck_map_nodes_one_link")
        ),
        sa.ForeignKeyConstraint(
            ["map_id"],
            ["idea_maps.id"],
            name=op.f("fk_map_nodes_map_id_idea_maps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["map_nodes.id"],
            name=op.f("fk_map_nodes_parent_id_map_nodes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_map_nodes_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_map_nodes_task_id_tasks"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_map_nodes")),
    )
    op.create_index("ix_map_nodes_map_id", "map_nodes", ["map_id"], unique=False)


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_index("ix_map_nodes_map_id", table_name="map_nodes")
    op.drop_table("map_nodes")
    op.drop_index("ix_ideas_step", table_name="ideas")
    op.drop_table("ideas")
    op.drop_table("idea_maps")
