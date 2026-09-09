"""Справочники: направления, приоритеты, статусы, настройки, организации

Первые таблицы системы. Хранят то, что принадлежит данным: название на трёх
письменностях, порядок, цвет, видимость. Смысл значений остаётся в коде
(`app.domain.dictionaries`) — иначе система не сможет понять, что означает статус,
заведённый через интерфейс.

Значения не заполняются здесь: наполнение — дело сидов (`python -m app.seed`), а не
миграции. Миграция описывает форму, данные меняются отдельно и без выпуска новой
версии — этого и требует ТЗ 6.8.

Ревизия: 0002_dictionaries
Предыдущая: 0001_baseline
Создана: 2026-09-09 08:42:19.241293
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_dictionaries"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "directions",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name_ru", sa.String(length=200), nullable=False),
        sa.Column("name_uz_cyrl", sa.String(length=200), nullable=False),
        sa.Column("name_uz_latn", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_directions")),
        sa.UniqueConstraint("code", name=op.f("uq_directions_code")),
        schema="orbita",
    )
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("short_name", sa.String(length=100), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "country_code IS NULL OR country_code = upper(country_code)",
            name=op.f("ck_organizations_country_code_upper"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        schema="orbita",
    )
    op.create_table(
        "priorities",
        sa.Column("color", sa.String(length=20), nullable=False),
        sa.Column("warn_days_override", sa.SmallInteger(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name_ru", sa.String(length=200), nullable=False),
        sa.Column("name_uz_cyrl", sa.String(length=200), nullable=False),
        sa.Column("name_uz_latn", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_priorities")),
        sa.UniqueConstraint("code", name=op.f("uq_priorities_code")),
        schema="orbita",
    )
    op.create_table(
        "project_statuses",
        sa.Column("is_terminal", sa.Boolean(), nullable=False),
        sa.Column("requires_reason", sa.Boolean(), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name_ru", sa.String(length=200), nullable=False),
        sa.Column("name_uz_cyrl", sa.String(length=200), nullable=False),
        sa.Column("name_uz_latn", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_statuses")),
        sa.UniqueConstraint("code", name=op.f("uq_project_statuses_code")),
        schema="orbita",
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description_ru", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(length=20), nullable=False),
        sa.Column("min_value", sa.Integer(), nullable=True),
        sa.Column("max_value", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
        sa.UniqueConstraint("key", name=op.f("uq_settings_key")),
        schema="orbita",
    )
    op.create_table(
        "task_statuses",
        sa.Column("is_terminal", sa.Boolean(), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name_ru", sa.String(length=200), nullable=False),
        sa.Column("name_uz_cyrl", sa.String(length=200), nullable=False),
        sa.Column("name_uz_latn", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_statuses")),
        sa.UniqueConstraint("code", name=op.f("uq_task_statuses_code")),
        schema="orbita",
    )


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_table("task_statuses", schema="orbita")
    op.drop_table("settings", schema="orbita")
    op.drop_table("project_statuses", schema="orbita")
    op.drop_table("priorities", schema="orbita")
    op.drop_table("organizations", schema="orbita")
    op.drop_table("directions", schema="orbita")
