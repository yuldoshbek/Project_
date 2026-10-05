"""Файлы и версии презентаций

Раздел «Файлы» (блок 2, ADR-0009) и версии презентаций докладов (ТЗ 3.5):

- **`stored_files`** — файл в хранилище: строка появляется, когда выдана ссылка на загрузку, и
  становится «сохранён», когда API проверил, что файл лёг;
- **`presentation_versions`** — номер версии, PDF, статус (на просмотре, на доработке, принята);
- **`slide_comments`** — замечание на слайд и в какой версии исправлено.

Сами файлы лежат в хранилище (`app.adapters.storage`), не в базе: откат удаляет только строки.

Ревизия: 0008_files
Предыдущая: 0007_preparations
Создана: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_files"
down_revision: str | None = "0007_preparations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("owner_type", sa.String(length=30), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=400), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "owner_type IN ('presentation_version')",
            name=op.f("ck_stored_files_owner_type_is_known"),
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'stored')", name=op.f("ck_stored_files_state_is_known")
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_stored_files_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_files")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_stored_files_storage_key")),
    )
    op.create_index(
        "ix_stored_files_owner_type_owner_id",
        "stored_files",
        ["owner_type", "owner_id"],
        unique=False,
    )
    op.create_table(
        "presentation_versions",
        sa.Column("preparation_id", sa.UUID(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
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
            "state IN ('review', 'rework', 'accepted')",
            name=op.f("ck_presentation_versions_state_is_known"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["stored_files.id"],
            name=op.f("fk_presentation_versions_file_id_stored_files"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["preparation_id"],
            ["preparations.id"],
            name=op.f("fk_presentation_versions_preparation_id_preparations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_presentation_versions_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_presentation_versions")),
        sa.UniqueConstraint(
            "preparation_id", "number", name=op.f("uq_presentation_versions_preparation_id_number")
        ),
    )
    op.create_table(
        "slide_comments",
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("slide", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("fixed_in_version_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("slide >= 1", name=op.f("ck_slide_comments_slide_is_positive")),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_slide_comments_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["fixed_in_version_id"],
            ["presentation_versions.id"],
            name=op.f("fk_slide_comments_fixed_in_version_id_presentation_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["presentation_versions.id"],
            name=op.f("fk_slide_comments_version_id_presentation_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_slide_comments")),
    )
    op.create_index("ix_slide_comments_version_id", "slide_comments", ["version_id"], unique=False)


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_index("ix_slide_comments_version_id", table_name="slide_comments")
    op.drop_table("slide_comments")
    op.drop_table("presentation_versions")
    op.drop_index("ix_stored_files_owner_type_owner_id", table_name="stored_files")
    op.drop_table("stored_files")
