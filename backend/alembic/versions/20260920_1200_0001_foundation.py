"""Базовая схема ORBITA под ТЗ v2.0

Одна миграция, и это не первая её редакция. 20.09 восемнадцать прежних миграций были
сведены в одну: они несли на себе снятые решения — гриф, вход по паролю, вложения с
антивирусом, обмен с SETA ([ADR-0027](../../../docs/adr/ADR-0027-rebuild-v3.md)). 25.09 та
же ревизия пересобрана по моделям под раздел 3 ТЗ v2.0: типы проектов с шаблонами вех,
подпроекты, роли организаций, решения руководителя, годовые циклы, поле версии у
редактируемых записей. Вторая миграция поверх первой воспроизводила бы при каждом накате
схему, которую тут же сносит, — а рабочей базы с данными ещё нет, и переписать начало
пока стоит одного файла.

Автогенерация видит не всё, поэтому руками здесь дописано:

- **Расширения PostgreSQL.** Без `pgcrypto` не выдать первичные ключи
  (`gen_random_uuid`), без `pg_trgm` и `unaccent` не собрать поиск по трём письменностям
  ([ADR-0006](../../../docs/adr/ADR-0006-multiscript-search.md)). Проверка стоит первой,
  чтобы отсутствие расширения обнаруживалось здесь, а не через десять таблиц на создании
  индекса — с сообщением о чём угодно, кроме причины. `citext` больше не нужен: столбцов
  этого типа в схеме нет — адреса почты у пользователей сняты вместе со входом по паролю.
- **Неизменяемость журнала.** Триггеры на `UPDATE`, `DELETE` и `TRUNCATE` плюс отзыв прав:
  журнал, который может подчистить тот же код, что в него пишет, ничего не доказывает
  ([ADR-0010](../../../docs/adr/ADR-0010-audit-log.md)).

Что автогенерация создаёт сама, но `alembic check` потом **не сравнивает** — ограничения
`CHECK`, условия частичных индексов, `NULLS NOT DISTINCT`. Их совпадение с моделями
сверено руками и стережётся тестами поведения (`test_ijro_schema`, `test_migrations`),
а не сравнением схем.

Схему `orbita` создаёт `env.py` до запуска миграций: Alembic должен где-то завести таблицу
версий, а она уже живёт в этой схеме.

Ревизия: 0001_foundation
Предыдущая: нет
Создана: 2026-09-20, пересобрана 2026-09-25
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
    ("pgcrypto", "gen_random_uuid для первичных ключей"),
    ("pg_trgm", "поиск с опечатками и частичным вводом"),
    ("unaccent", "снятие диакритики при нормализации поискового текста"),
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
        # EXTENSION требует прав, которых у приложения быть не должно. Попытка всё же
        # делается: там, где прав хватает, миграция проходит сама.
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
    """Снимает защиту журнала — только ради отката, перед удалением самой таблицы.

    Порядок важен: пока триггеры на месте, `DROP TABLE` проходит (удаление таблицы не
    `DELETE` и не `TRUNCATE`), но функция, на которую они ссылаются, не удаляется раньше
    них.
    """
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
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("is_founded_by_agency", sa.Boolean(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=True),
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
            "kind IN ('ministry', 'agency', 'khokimiyat', 'international', 'company')",
            name=op.f("ck_organizations_kind_is_known"),
        ),
        sa.CheckConstraint(
            "country_code IS NULL OR country_code = upper(country_code)",
            name=op.f("ck_organizations_country_code_upper"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("name", name=op.f("uq_organizations_name")),
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
        "project_types",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_types")),
        sa.UniqueConstraint("code", name=op.f("uq_project_types_code")),
    )
    op.create_table(
        "regions",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_regions")),
        sa.UniqueConstraint("code", name=op.f("uq_regions_code")),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("value_type", sa.String(length=20), nullable=False),
        sa.Column("description_ru", sa.Text(), nullable=False),
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
        "task_types",
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_types")),
        sa.UniqueConstraint("code", name=op.f("uq_task_types_code")),
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
        "people",
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("position", sa.String(length=200), nullable=True),
        sa.Column("department", sa.String(length=200), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_people_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_people")),
    )
    op.create_index("ix_people_full_name", "people", ["full_name"], unique=False)
    op.create_table(
        "project_type_milestones",
        sa.Column("project_type_id", sa.UUID(), nullable=False),
        sa.Column("offset_days", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
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
        sa.CheckConstraint(
            "offset_days >= 0", name=op.f("ck_project_type_milestones_offset_is_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["project_type_id"],
            ["project_types.id"],
            name=op.f("fk_project_type_milestones_project_type_id_project_types"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_type_milestones")),
        sa.UniqueConstraint(
            "project_type_id",
            "sort_order",
            name=op.f("uq_project_type_milestones_project_type_id_sort_order"),
        ),
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
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_visit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('assistant', 'leader')", name=op.f("ck_users_role_is_known")),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["people.id"],
            name=op.f("fk_users_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("role", name=op.f("uq_users_role")),
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
            "entity_type IN ('ijro_assignment')", name=op.f("ck_comments_entity_type_is_known")
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
        "leader_decisions",
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("assignee_person_id", sa.UUID(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("done_on", sa.Date(), nullable=True),
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
            "(state = 'done' AND done_on IS NOT NULL) OR (state = 'open' AND done_on IS NULL)",
            name=op.f("ck_leader_decisions_done_decision_has_a_date"),
        ),
        sa.CheckConstraint(
            "kind IN ('approve', 'return', 'assign', 'hurry', 'escalate', 'ask_extension', "
            "'reject')",
            name=op.f("ck_leader_decisions_kind_is_known"),
        ),
        sa.CheckConstraint(
            "state IN ('open', 'done')", name=op.f("ck_leader_decisions_state_is_known")
        ),
        sa.CheckConstraint(
            "target_type IN ('project', 'task', 'milestone', 'ijro_assignment')",
            name=op.f("ck_leader_decisions_target_type_is_known"),
        ),
        sa.ForeignKeyConstraint(
            ["assignee_person_id"],
            ["people.id"],
            name=op.f("fk_leader_decisions_assignee_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_leader_decisions_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leader_decisions")),
    )
    op.create_index(
        "ix_leader_decisions_state_due_on", "leader_decisions", ["state", "due_on"], unique=False
    )
    op.create_index(
        "ix_leader_decisions_target_type_target_id",
        "leader_decisions",
        ["target_type", "target_id"],
        unique=False,
    )
    op.create_table(
        "leader_questions",
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("asked_by", sa.UUID(), nullable=True),
        sa.Column("decision_id", sa.UUID(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
            "decision_id IS NULL OR closed_at IS NOT NULL",
            name=op.f("ck_leader_questions_answered_question_is_closed"),
        ),
        sa.CheckConstraint(
            "target_type IN ('project', 'task', 'milestone', 'ijro_assignment')",
            name=op.f("ck_leader_questions_target_type_is_known"),
        ),
        sa.ForeignKeyConstraint(
            ["asked_by"],
            ["users.id"],
            name=op.f("fk_leader_questions_asked_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["leader_decisions.id"],
            name=op.f("fk_leader_questions_decision_id_leader_decisions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leader_questions")),
    )
    op.create_index(
        "ix_leader_questions_open_target",
        "leader_questions",
        ["target_type", "target_id"],
        unique=False,
        postgresql_where="closed_at IS NULL",
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
        sa.Column("project_type_id", sa.UUID(), nullable=False),
        sa.Column("parent_project_id", sa.UUID(), nullable=True),
        sa.Column("is_multiyear", sa.Boolean(), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("original_due_on", sa.Date(), nullable=False),
        sa.Column("status_code", sa.String(length=50), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("responsible_person_id", sa.UUID(), nullable=True),
        sa.Column("direction_id", sa.UUID(), nullable=True),
        sa.Column("region_id", sa.UUID(), nullable=True),
        sa.Column("impediment", sa.Text(), nullable=True),
        sa.Column("impediment_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
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
            "status_code NOT IN ('on_hold', 'cancelled') "
            "OR (status_reason IS NOT NULL AND btrim(status_reason) <> '')",
            name=op.f("ck_projects_paused_and_cancelled_need_a_reason"),
        ),
        sa.CheckConstraint(
            "due_on >= started_on", name=op.f("ck_projects_due_on_is_not_before_started_on")
        ),
        sa.CheckConstraint(
            "parent_project_id <> id", name=op.f("ck_projects_project_is_not_its_own_parent")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_projects_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["direction_id"], ["directions.id"], name=op.f("fk_projects_direction_id_directions")
        ),
        sa.ForeignKeyConstraint(
            ["parent_project_id"],
            ["projects.id"],
            name=op.f("fk_projects_parent_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_type_id"],
            ["project_types.id"],
            name=op.f("fk_projects_project_type_id_project_types"),
        ),
        sa.ForeignKeyConstraint(
            ["region_id"], ["regions.id"], name=op.f("fk_projects_region_id_regions")
        ),
        sa.ForeignKeyConstraint(
            ["responsible_person_id"],
            ["people.id"],
            name=op.f("fk_projects_responsible_person_id_people"),
            ondelete="SET NULL",
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
        "ix_projects_multiyear_due_on",
        "projects",
        ["due_on"],
        unique=False,
        postgresql_where="is_multiyear",
    )
    op.create_index(
        "ix_projects_parent_project_id", "projects", ["parent_project_id"], unique=False
    )
    op.create_index(
        "ix_projects_responsible_person_id_due_on",
        "projects",
        ["responsible_person_id", "due_on"],
        unique=False,
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
            "due_precision IN ('exact', 'end_of_year')",
            name=op.f("ck_ijro_assignments_due_precision_is_known"),
        ),
        sa.CheckConstraint(
            "due_year_source IS NULL OR due_year_source IN ('from_header', 'from_block', 'manual')",
            name=op.f("ck_ijro_assignments_due_year_source_is_known"),
        ),
        sa.CheckConstraint(
            "state IN ('not_started', 'in_progress', 'blocked_by_lead', 'submitted', 'done', "
            "'removed_from_control')",
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
            postgresql_nulls_not_distinct=True,
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
        sa.Column("original_due_on", sa.Date(), nullable=False),
        sa.Column("is_passed", sa.Boolean(), nullable=False),
        sa.Column("passed_on", sa.Date(), nullable=True),
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
        sa.CheckConstraint(
            "(is_passed AND passed_on IS NOT NULL) OR (NOT is_passed AND passed_on IS NULL)",
            name=op.f("ck_milestones_passed_milestone_has_a_date"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_milestones_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestones")),
    )
    op.create_index(
        "ix_milestones_due_on",
        "milestones",
        ["due_on"],
        unique=False,
        postgresql_where="NOT is_passed",
    )
    op.create_index(
        "ix_milestones_project_id_sort_order",
        "milestones",
        ["project_id", "sort_order"],
        unique=False,
    )
    op.create_table(
        "project_organizations",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
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
            "role IN ('customer', 'executor', 'co_executor', 'lead_agency')",
            name=op.f("ck_project_organizations_role_is_known"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_project_organizations_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_organizations_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_organizations")),
    )
    op.create_index(
        "ix_project_organizations_organization_id_role",
        "project_organizations",
        ["organization_id", "role"],
        unique=False,
    )
    op.create_index(
        "uq_project_organizations_project_id_organization_id",
        "project_organizations",
        ["project_id", "organization_id"],
        unique=True,
    )
    op.create_table(
        "yearly_cycles",
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("rule", sa.String(length=20), nullable=False),
        sa.Column("month", sa.SmallInteger(), nullable=False),
        sa.Column("day", sa.SmallInteger(), nullable=False),
        sa.Column("every_years", sa.SmallInteger(), nullable=False),
        sa.Column("anchor_year", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("responsible_person_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
            "rule IN ('annual', 'quarterly', 'every_n_years')",
            name=op.f("ck_yearly_cycles_rule_is_known"),
        ),
        sa.CheckConstraint("day BETWEEN 1 AND 31", name=op.f("ck_yearly_cycles_day_is_a_day")),
        sa.CheckConstraint(
            "every_years BETWEEN 1 AND 10", name=op.f("ck_yearly_cycles_every_years_is_sane")
        ),
        sa.CheckConstraint(
            "month BETWEEN 1 AND 12", name=op.f("ck_yearly_cycles_month_is_a_month")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_yearly_cycles_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["responsible_person_id"],
            ["people.id"],
            name=op.f("fk_yearly_cycles_responsible_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_yearly_cycles")),
    )
    op.create_index("ix_yearly_cycles_project_id", "yearly_cycles", ["project_id"], unique=False)
    op.create_table(
        "tasks",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_type_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("ijro_assignment_id", sa.UUID(), nullable=True),
        sa.Column("assignee_person_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["assignee_person_id"],
            ["people.id"],
            name=op.f("fk_tasks_assignee_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ijro_assignment_id"],
            ["ijro_assignments.id"],
            name=op.f("fk_tasks_ijro_assignment_id_ijro_assignments"),
            ondelete="SET NULL",
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
        sa.ForeignKeyConstraint(
            ["task_type_id"], ["task_types.id"], name=op.f("fk_tasks_task_type_id_task_types")
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
    op.create_index("ix_tasks_ijro_assignment_id", "tasks", ["ijro_assignment_id"], unique=False)
    op.create_index("ix_tasks_project_id_status", "tasks", ["project_id", "status"], unique=False)
    op.create_index("ix_tasks_status_due_at", "tasks", ["status", "due_at"], unique=False)
    op.create_table(
        "task_checklist_items",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_done", sa.Boolean(), nullable=False),
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

    protect_audit_log()


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция, которую
    # нельзя применить в рабочем контуре. Расширения при откате не удаляются: они
    # принадлежат базе, а не нашей схеме, и ими может пользоваться сосед.
    unprotect_audit_log()

    op.drop_index("ix_task_checklist_items_task_id_sort_order", table_name="task_checklist_items")
    op.drop_table("task_checklist_items")
    op.drop_index("ix_tasks_status_due_at", table_name="tasks")
    op.drop_index("ix_tasks_project_id_status", table_name="tasks")
    op.drop_index("ix_tasks_ijro_assignment_id", table_name="tasks")
    op.drop_index("ix_tasks_assignee_person_id_status", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_yearly_cycles_project_id", table_name="yearly_cycles")
    op.drop_table("yearly_cycles")
    op.drop_index(
        "uq_project_organizations_project_id_organization_id", table_name="project_organizations"
    )
    op.drop_index(
        "ix_project_organizations_organization_id_role", table_name="project_organizations"
    )
    op.drop_table("project_organizations")
    op.drop_index("ix_milestones_project_id_sort_order", table_name="milestones")
    op.drop_index("ix_milestones_due_on", table_name="milestones", postgresql_where="NOT is_passed")
    op.drop_table("milestones")
    op.drop_index("ix_ijro_assignments_state_due_on", table_name="ijro_assignments")
    op.drop_index("ix_ijro_assignments_responsible_person_id_due_on", table_name="ijro_assignments")
    op.drop_table("ijro_assignments")
    op.drop_index("ix_sessions_user_id_expires_at", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_projects_status_code_due_on", table_name="projects")
    op.drop_index("ix_projects_responsible_person_id_due_on", table_name="projects")
    op.drop_index("ix_projects_parent_project_id", table_name="projects")
    op.drop_index(
        "ix_projects_multiyear_due_on", table_name="projects", postgresql_where="is_multiyear"
    )
    op.drop_table("projects")
    op.drop_index("ix_notifications_user_id_created_at", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(
        "ix_leader_questions_open_target",
        table_name="leader_questions",
        postgresql_where="closed_at IS NULL",
    )
    op.drop_table("leader_questions")
    op.drop_index("ix_leader_decisions_target_type_target_id", table_name="leader_decisions")
    op.drop_index("ix_leader_decisions_state_due_on", table_name="leader_decisions")
    op.drop_table("leader_decisions")
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
    op.drop_table("project_type_milestones")
    op.drop_index("ix_people_full_name", table_name="people")
    op.drop_table("people")
    op.drop_table("ijro_org_aliases")
    op.drop_table("task_types")
    op.drop_table("task_statuses")
    op.drop_table("settings")
    op.drop_table("regions")
    op.drop_table("project_types")
    op.drop_table("project_statuses")
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
