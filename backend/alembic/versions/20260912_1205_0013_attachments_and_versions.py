"""Вложения и версии

Две таблицы, а не одна (ADR-0009). `documents` — логический файл: кому принадлежит, как
называется, какая версия сейчас. `document_versions` — само содержимое: размер, тип,
отпечаток, ключ в хранилище. Одна таблица означала бы, что «Смета.xlsx» и «Смета.xlsx
(2)» — две независимые записи, и вопрос «какая последняя» решался бы сравнением времени
загрузки у файлов с одинаковым именем.

Имя документа — CITEXT: «Смета.xlsx» и «смета.xlsx» это один документ. Регистр в имени
файла ставят не думая, и два документа из-за заглавной буквы — ровно та путаница, ради
которой версии и заводились.

Уникальность имени у владельца — **частичным** индексом, только по неудалённым. Иначе
файл, удалённый по ошибке, нельзя загрузить заново под тем же именем, а это первое, что
человек попробует.

Содержимого файлов в базе нет: оно лежит в S3-совместимом хранилище, здесь — только
ключ. Резервное копирование обязано покрывать и то, и другое согласованно (ТЗ 10.4,
ORB-047): база без бакета — это список файлов, которых нет.

`sha256` под индексом: по нему отсекается повторная загрузка того же содержимого — версия,
не отличающаяся от предыдущей ни байтом, это не история, а шум.

Ревизия: 0013_attachments_and_versions
Предыдущая: 0012_comments_and_notifications
Создана: 2026-09-12 12:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_attachments_and_versions"
down_revision: str | None = "0012_comments_and_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("name", postgresql.CITEXT(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "entity_type IN ('project', 'task')", name=op.f("ck_documents_entity_type_is_known")
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 255", name=op.f("ck_documents_name_length_is_sane")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index(
        "ix_documents_entity_type_entity_id",
        "documents",
        ["entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "uq_documents_entity_type_entity_id_name",
        "documents",
        ["entity_type", "entity_id", "name"],
        unique=True,
        postgresql_where="deleted_at IS NULL",
    )
    op.create_table(
        "document_versions",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("preview_state", sa.String(length=20), nullable=False),
        sa.Column("preview_key", sa.String(length=500), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "preview_state IN ('native', 'pending', 'ready', 'failed', 'unsupported')",
            name=op.f("ck_document_versions_preview_state_is_known"),
        ),
        sa.CheckConstraint("number > 0", name=op.f("ck_document_versions_number_is_positive")),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_document_versions_size_is_positive")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_versions_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_document_versions_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_versions")),
        sa.UniqueConstraint(
            "document_id", "number", name="uq_document_versions_document_id_number"
        ),
        sa.UniqueConstraint("storage_key", name=op.f("uq_document_versions_storage_key")),
    )
    op.create_index("ix_document_versions_sha256", "document_versions", ["sha256"], unique=False)


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_index("ix_document_versions_sha256", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index(
        "uq_documents_entity_type_entity_id_name",
        table_name="documents",
        postgresql_where="deleted_at IS NULL",
    )
    op.drop_index("ix_documents_entity_type_entity_id", table_name="documents")
    op.drop_table("documents")
