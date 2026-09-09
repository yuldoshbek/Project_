"""Пользователи системы и справочник сотрудников агентства

Две таблицы для двух разных понятий (`app.domain.people`): `users` — те двое, кто
входит в систему; `people` — десятки сотрудников агентства, на которых записана
работа, но которые в ORBITA не входят.

Счётчик неудачных попыток входа и время блокировки хранятся в записи пользователя, а
не в памяти процесса: в памяти они обнулялись бы при перезапуске и не учитывались бы
воркером и ботом — ограничение частоты существовало бы только на бумаге.

Ревизия: 0003_users_people
Предыдущая: 0002_dictionaries
Создана: 2026-09-09 09:02:12.046934
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_users_people"
down_revision: str | None = "0002_dictionaries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "people",
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("position", sa.String(length=200), nullable=True),
        sa.Column("department", sa.String(length=200), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_people")),
        schema="orbita",
    )
    op.create_index("ix_people_full_name", "people", ["full_name"], unique=False, schema="orbita")
    op.create_table(
        "users",
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("telegram_id", sa.Integer(), nullable=True),
        sa.Column("external_seta_id", sa.String(length=100), nullable=True),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_count", sa.SmallInteger(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
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
            ["orbita.people.id"],
            name=op.f("fk_users_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("external_seta_id", name=op.f("uq_users_external_seta_id")),
        sa.UniqueConstraint("telegram_id", name=op.f("uq_users_telegram_id")),
        schema="orbita",
    )


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_table("users", schema="orbita")
    op.drop_index("ix_people_full_name", table_name="people", schema="orbita")
    op.drop_table("people", schema="orbita")
