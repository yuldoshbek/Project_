"""Реестр «Ижро»: документы, поручения, псевдонимы, привоз

Пять таблиц по [ADR-0025](../../../docs/adr/ADR-0025-ijro-standalone-register.md). Реестр
спроектирован по настоящим данным заказчика — трём годовым контрольным таблицам и разбору
проблемных поручений, — и каждое ограничение ниже выведено из счёта, а не из привычки.

**Ключ повтора `(document_id, band, due_on)`** проверен на всех 165 строках: он даёт 164
группы, а единственное слипание — строка, приведённая в источнике дважды байт в байт. Без
срока ключ не годится: 23 пары «документ + пункт» законно повторяются по месяцам, это
регулярные поручения, и слияние потеряло бы три срока из четырёх.

**`band` допускает NULL** — одна строка из 165 пункта не имеет вовсе. `NOT NULL` выбросил
бы её из реестра.

**`ijro_documents` — отдельная таблица**, потому что 57 документов порождают 164 поручения
и вопрос руководителя задаётся про документ: ПФ-155 встречается 32 раза в двух написаниях.

**Проверка `co_executor_has_a_lead_organization`** запрещает признак «мы соисполнители»
без ведомства: таких строк 55 из 165, по ним собирается список «что сорвётся не по нашей
вине», и пустая ссылка сделала бы строку в нём невидимой.

**`comments` и `documents` получают третьего владельца.** Своей ленты и своего хранилища
реестр не заводит: обе таблицы уже полиморфны, и вторая лента однажды разошлась бы с
первой по поведению. Автогенерация правку `CHECK` не видит — текст ограничения для неё
непрозрачен, — поэтому она сделана руками, и обратная сторона тоже.

Ревизия: 0018_ijro_registry
Предыдущая: 0017_drop_login
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_ijro_registry"
down_revision: str | None = "0017_drop_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _retarget_polymorphic_checks("'project', 'task', 'ijro_assignment'")

    op.create_table(
        "ijro_documents",
        sa.Column("code_norm", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("number_raw", sa.String(length=120), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("title_raw", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('farmon', 'qaror', 'qonun', 'bayon', 'topshiriq', 'other')",
            name=op.f("ck_ijro_documents_kind_is_known"),
        ),
        sa.CheckConstraint(
            "source IN ('pa', 'vm', 'legal')", name=op.f("ck_ijro_documents_source_is_known")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ijro_documents")),
        sa.UniqueConstraint("code_norm", name=op.f("uq_ijro_documents_code_norm")),
    )
    op.create_index(
        "ix_ijro_documents_source_issued_on",
        "ijro_documents",
        ["source", "issued_on"],
        unique=False,
    )
    op.create_table(
        "ijro_org_aliases",
        sa.Column("alias_norm", sa.String(length=300), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source IN ('auto', 'manual')", name=op.f("ck_ijro_org_aliases_source_is_known")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_ijro_org_aliases_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ijro_org_aliases")),
        sa.UniqueConstraint("alias_norm", name=op.f("uq_ijro_org_aliases_alias_norm")),
    )
    op.create_table(
        "ijro_person_aliases",
        sa.Column("alias_norm", sa.String(length=200), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source IN ('auto', 'manual')", name=op.f("ck_ijro_person_aliases_source_is_known")
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.id"],
            name=op.f("fk_ijro_person_aliases_person_id_people"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ijro_person_aliases")),
        sa.UniqueConstraint("alias_norm", name=op.f("uq_ijro_person_aliases_alias_norm")),
    )
    op.create_table(
        "ijro_imports",
        sa.Column("filename", sa.String(length=400), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=400), nullable=True),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=10), nullable=True),
        sa.Column("table_year", sa.Integer(), nullable=True),
        sa.Column("rows_total", sa.Integer(), nullable=False),
        sa.Column("rows_new", sa.Integer(), nullable=False),
        sa.Column("rows_changed", sa.Integer(), nullable=False),
        sa.Column("rows_unrecognized", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "report",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source IS NULL OR source IN ('pa', 'vm', 'legal')",
            name=op.f("ck_ijro_imports_source_is_known"),
        ),
        sa.CheckConstraint(
            "state IN ('preview', 'applied', 'discarded')",
            name=op.f("ck_ijro_imports_state_is_known"),
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_ijro_imports_uploaded_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ijro_imports")),
    )
    op.create_index(
        "uq_ijro_imports_sha256_applied",
        "ijro_imports",
        ["sha256"],
        unique=True,
        postgresql_where="state = 'applied'",
    )
    op.create_table(
        "ijro_assignments",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("band", sa.String(length=60), nullable=True),
        sa.Column("band_sort", sa.String(length=60), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("mechanism", sa.Text(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("due_raw", sa.String(length=100), nullable=True),
        sa.Column("due_precision", sa.String(length=20), nullable=False),
        sa.Column("due_year_source", sa.String(length=20), nullable=True),
        sa.Column("block_label", sa.String(length=40), nullable=True),
        sa.Column("responsible_raw", sa.String(length=400), nullable=True),
        sa.Column("responsible_person_id", sa.UUID(), nullable=True),
        sa.Column("lead_organization_id", sa.UUID(), nullable=True),
        sa.Column("is_co_executor", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("problem", sa.Text(), nullable=True),
        sa.Column("proposal", sa.Text(), nullable=True),
        sa.Column("problem_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_state_raw", sa.String(length=400), nullable=True),
        sa.Column("import_batch_id", sa.UUID(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_in_import_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "due_precision IN ('exact', 'end_of_year')",
            name=op.f("ck_ijro_assignments_due_precision_is_known"),
        ),
        sa.CheckConstraint(
            "due_year_source IS NULL OR due_year_source IN ('from_header', 'from_block', 'manual')",
            name=op.f("ck_ijro_assignments_due_year_source_is_known"),
        ),
        sa.CheckConstraint(
            "state IN ('not_started', 'in_progress', 'blocked_by_lead', "
            "'submitted', 'done', 'removed_from_control')",
            name=op.f("ck_ijro_assignments_state_is_known"),
        ),
        sa.CheckConstraint(
            "is_co_executor IS FALSE OR lead_organization_id IS NOT NULL",
            name=op.f("ck_ijro_assignments_co_executor_has_a_lead_organization"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["ijro_documents.id"],
            name=op.f("fk_ijro_assignments_document_id_ijro_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["ijro_imports.id"],
            name=op.f("fk_ijro_assignments_import_batch_id_ijro_imports"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lead_organization_id"],
            ["organizations.id"],
            name=op.f("fk_ijro_assignments_lead_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["responsible_person_id"],
            ["people.id"],
            name=op.f("fk_ijro_assignments_responsible_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ijro_assignments")),
        sa.UniqueConstraint("code", name=op.f("uq_ijro_assignments_code")),
        sa.UniqueConstraint(
            "document_id",
            "band",
            "due_on",
            name=op.f("uq_ijro_assignments_document_id_band_due_on"),
        ),
    )
    op.create_index(
        "ix_ijro_assignments_responsible_person_id_due_on",
        "ijro_assignments",
        ["responsible_person_id", "due_on"],
        unique=False,
    )
    op.create_index(
        "ix_ijro_assignments_state_due_on", "ijro_assignments", ["state", "due_on"], unique=False
    )


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("ix_ijro_assignments_state_due_on", table_name="ijro_assignments")
    op.drop_index("ix_ijro_assignments_responsible_person_id_due_on", table_name="ijro_assignments")
    op.drop_table("ijro_assignments")
    op.drop_index(
        "uq_ijro_imports_sha256_applied",
        table_name="ijro_imports",
        postgresql_where="state = 'applied'",
    )
    op.drop_table("ijro_imports")
    op.drop_table("ijro_person_aliases")
    op.drop_table("ijro_org_aliases")
    op.drop_index("ix_ijro_documents_source_issued_on", table_name="ijro_documents")
    op.drop_table("ijro_documents")

    _retarget_polymorphic_checks("'project', 'task'")


def _retarget_polymorphic_checks(targets: str) -> None:
    """Переписывает `CHECK` у `comments` и `documents` под новый набор владельцев.

    Одна функция на оба направления: списки владельцев в прямой и обратной миграции —
    единственное, чем они отличаются, и продублированный DDL разошёлся бы при следующей
    правке. Ограничение снимается и создаётся заново: изменить текст `CHECK` на месте
    PostgreSQL не умеет.
    """
    for table in ("comments", "documents"):
        # Короткое имя: соглашение об именовании из `repos.base` само добавит
        # префикс `ck_<таблица>_`. Полное имя получило бы его второй раз.
        op.drop_constraint("entity_type_is_known", table, type_="check")
        op.create_check_constraint("entity_type_is_known", table, f"entity_type IN ({targets})")
