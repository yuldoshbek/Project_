"""Базовая схема ORBITA

Одна миграция вместо восемнадцати прежних. Так сделано не ради красоты истории: прежние
восемнадцать несли на себе снятые решения — гриф и признак выдачи наружу, вход по паролю,
вложения с антивирусом, обмен с SETA, — и накат чистой базы воспроизводил их, чтобы
следующая миграция тут же убрала. Рабочей базы с реальными данными ещё нет, поэтому это
последний момент, когда историю можно свести к одному честному началу
([ADR-0027](../../../docs/adr/ADR-0027-rebuild-v3.md)).

Что здесь есть, кроме таблиц:

- **Расширения PostgreSQL.** Без `pg_trgm` и `unaccent` не собрать поиск, без `pgcrypto`
  не выдать первичные ключи, без `citext` не работает регистронезависимый адрес почты.
  Проверка стоит первой, чтобы отсутствие расширения обнаруживалось здесь, а не через
  десять таблиц на создании индекса — с сообщением о чём угодно, кроме причины.
- **Неизменяемость журнала.** Триггеры и отзыв прав: журнал, который может подчистить тот
  же код, что в него пишет, ничего не доказывает
  ([ADR-0010](../../../docs/adr/ADR-0010-audit-log.md)).

Схему `orbita` создаёт `env.py` до запуска миграций: Alembic должен где-то завести таблицу
версий, а она уже живёт в этой схеме.

Ревизия: 0001_foundation
Предыдущая: нет
Создана: 2026-09-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REQUIRED_EXTENSIONS: tuple[tuple[str, str], ...] = (
    ("pg_trgm", "поиск с опечатками и частичным вводом"),
    ("unaccent", "снятие диакритики при нормализации поискового текста"),
    ("citext", "регистронезависимый адрес электронной почты"),
    ("pgcrypto", "gen_random_uuid для первичных ключей"),
)

APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Журнал изменений неизменяем: операция % запрещена', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;
"""


def create_extensions() -> None:
    connection = op.get_bind()
    for name, purpose in REQUIRED_EXTENSIONS:
        installed = connection.scalar(
            sa.text("SELECT 1 FROM pg_extension WHERE extname = :name"),
            {"name": name},
        )
        if installed:
            continue

        # В разработке расширения включает init-скрипт контейнера, в облаке они уже
        # установлены, на сервере агентства их поставит администратор базы: CREATE
        # EXTENSION требует прав суперпользователя, которых у приложения быть не должно.
        # Попытка всё же делается: там, где прав хватает, миграция проходит сама.
        try:
            connection.exec_driver_sql(f'CREATE EXTENSION IF NOT EXISTS "{name}"')
        except sa.exc.DBAPIError as error:
            raise RuntimeError(
                f"расширение PostgreSQL {name!r} не установлено и не может быть создано "
                f"приложением. Нужно для: {purpose}. "
                "Установите его от имени суперпользователя базы и повторите миграцию."
            ) from error


def protect_audit_log() -> None:
    """Делает журнал неизменяемым средствами самой базы."""
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
    # командой, и все предыдущие защиты оказываются декорацией.
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only()"
    )
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM PUBLIC")


def unprotect_audit_log() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_append_only()")


def upgrade() -> None:
    create_extensions()

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
    )
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
        "job_runs",
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_runs")),
    )
    op.create_index(
        "uq_job_runs_name_period",
        "job_runs",
        ["name", "period"],
        unique=True,
        postgresql_where=sa.text("status <> 'failed'"),
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
    )
    op.create_table(
        "people",
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("position", sa.String(length=200), nullable=True),
        sa.Column("department", sa.String(length=200), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("external_seta_id", sa.String(length=100), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_people")),
        sa.UniqueConstraint("external_seta_id", name=op.f("uq_people_external_seta_id")),
    )
    op.create_index("ix_people_full_name", "people", ["full_name"], unique=False)
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
    )
    op.create_table(
        "tags",
        sa.Column("name", postgresql.CITEXT(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 50", name=op.f("ck_tags_name_length")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("name", name=op.f("uq_tags_name")),
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
        "users",
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("external_seta_id", sa.String(length=100), nullable=True),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.id"],
            name=op.f("fk_users_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("external_seta_id", name=op.f("uq_users_external_seta_id")),
        sa.UniqueConstraint("telegram_id", name=op.f("uq_users_telegram_id")),
    )
    op.create_table(
        "access_links",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uses", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_access_links_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_links")),
        sa.UniqueConstraint("token_fingerprint", name=op.f("uq_access_links_token_fingerprint")),
        sa.UniqueConstraint("user_id", name=op.f("uq_access_links_user_id")),
    )
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
    op.create_table(
        "comments",
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
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
            "entity_type IN ('project', 'task', 'ijro_assignment')",
            name=op.f("ck_comments_entity_type_is_known"),
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_comments_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
    )
    op.create_index(
        "ix_comments_entity_type_entity_id_created_at",
        "comments",
        ["entity_type", "entity_id", "created_at"],
        unique=False,
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
        "notifications",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("dedup_key", sa.String(length=200), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("dedup_key", name=op.f("uq_notifications_dedup_key")),
    )
    op.create_index(
        "ix_notifications_user_id_created_at",
        "notifications",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "projects",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
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
        sa.Column("impediment", sa.Text(), nullable=True),
        sa.Column("impediment_updated_at", sa.DateTime(timezone=True), nullable=True),
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
            "status_code NOT IN ('on_hold', 'cancelled') OR (status_reason IS NOT NULL AND btrim(status_reason) <> '')",  # noqa: E501
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
    op.create_table(
        "sessions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_fingerprint", name=op.f("uq_sessions_token_fingerprint")),
    )
    op.create_index(
        "ix_sessions_user_id_expires_at", "sessions", ["user_id", "expires_at"], unique=False
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
            "state IN ('not_started', 'in_progress', 'blocked_by_lead', 'submitted', 'done', 'removed_from_control')",  # noqa: E501
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
    op.create_table(
        "milestones",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('planned', 'done')", name=op.f("ck_milestones_state_is_planned_or_done")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_milestones_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestones")),
    )
    op.create_index("ix_milestones_due_on", "milestones", ["due_on"], unique=False)
    op.create_index(
        "ix_milestones_project_id_sort_order",
        "milestones",
        ["project_id", "sort_order"],
        unique=False,
    )
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
    op.create_table(
        "tasks",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assignee_person_id", sa.UUID(), nullable=True),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority_code", sa.String(length=50), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_control", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assignee_person_id"],
            ["people.id"],
            name=op.f("fk_tasks_assignee_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_tasks_author_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["priority_code"], ["priorities.code"], name=op.f("fk_tasks_priority_code_priorities")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_tasks_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["status"], ["task_statuses.code"], name=op.f("fk_tasks_status_task_statuses")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
        sa.UniqueConstraint("code", name=op.f("uq_tasks_code")),
    )
    op.create_index(
        "ix_tasks_assignee_person_id_status",
        "tasks",
        ["assignee_person_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_tasks_project_id_status_due_at",
        "tasks",
        ["project_id", "status", "due_at"],
        unique=False,
    )
    op.create_index("ix_tasks_status_due_at", "tasks", ["status", "due_at"], unique=False)
    op.create_table(
        "task_checklist_items",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_done", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_checklist_items_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_checklist_items")),
    )
    op.create_index(
        "ix_task_checklist_items_task_id_sort_order",
        "task_checklist_items",
        ["task_id", "sort_order"],
        unique=False,
    )
    op.create_table(
        "task_tags",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("tag_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], name=op.f("fk_task_tags_tag_id_tags"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_task_tags_task_id_tasks"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_tags")),
        sa.UniqueConstraint("task_id", "tag_id", name=op.f("uq_task_tags_task_id_tag_id")),
    )
    op.create_index("ix_task_tags_tag_id", "task_tags", ["tag_id"], unique=False)
    protect_audit_log()


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция, которую
    # нельзя применить в рабочем контуре. Расширения при откате не удаляются: они
    # принадлежат базе, а не нашей схеме, и ими может пользоваться сосед.
    unprotect_audit_log()

    op.drop_index("ix_task_tags_tag_id", table_name="task_tags")
    op.drop_table("task_tags")
    op.drop_index("ix_task_checklist_items_task_id_sort_order", table_name="task_checklist_items")
    op.drop_table("task_checklist_items")
    op.drop_index("ix_tasks_status_due_at", table_name="tasks")
    op.drop_index("ix_tasks_project_id_status_due_at", table_name="tasks")
    op.drop_index("ix_tasks_assignee_person_id_status", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_project_partners_organization_id", table_name="project_partners")
    op.drop_table("project_partners")
    op.drop_index("ix_milestones_project_id_sort_order", table_name="milestones")
    op.drop_index("ix_milestones_due_on", table_name="milestones")
    op.drop_table("milestones")
    op.drop_index("ix_ijro_assignments_state_due_on", table_name="ijro_assignments")
    op.drop_index("ix_ijro_assignments_responsible_person_id_due_on", table_name="ijro_assignments")
    op.drop_table("ijro_assignments")
    op.drop_index("ix_sessions_user_id_expires_at", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_projects_status_code_due_on", table_name="projects")
    op.drop_index("ix_projects_direction_id_due_on", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_notifications_user_id_created_at", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(
        "uq_ijro_imports_sha256_applied",
        table_name="ijro_imports",
        postgresql_where="state = 'applied'",
    )
    op.drop_table("ijro_imports")
    op.drop_index("ix_comments_entity_type_entity_id_created_at", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
    op.drop_index("ix_audit_log_entity_type_entity_id_occurred_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("access_links")
    op.drop_table("users")
    op.drop_table("ijro_person_aliases")
    op.drop_table("ijro_org_aliases")
    op.drop_table("task_statuses")
    op.drop_table("tags")
    op.drop_table("settings")
    op.drop_table("project_statuses")
    op.drop_table("priorities")
    op.drop_index("ix_people_full_name", table_name="people")
    op.drop_table("people")
    op.drop_table("organizations")
    op.drop_index(
        "uq_job_runs_name_period",
        table_name="job_runs",
        postgresql_where=sa.text("status <> 'failed'"),
    )
    op.drop_table("job_runs")
    op.drop_index("ix_ijro_documents_source_issued_on", table_name="ijro_documents")
    op.drop_table("ijro_documents")
    op.drop_table("directions")
