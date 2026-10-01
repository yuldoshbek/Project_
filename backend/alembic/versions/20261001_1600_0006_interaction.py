"""Взаимодействие: письма, соглашения, контакты организации

Экран «Взаимодействие» утверждён заказчиком 01.10.2026, и схема меняется под него
(CLAUDE.md, цикл блока «экран → API»):

- **`letters`** — письма, где нужен ответ или действие руководителя либо стоит срок (ТЗ 3.4):
  направление, организация, тема, номер, дата, срок ответа, автор, связь с проектом или
  поручением, ответ, оценка ответа руководителем (V38);
- **`agreements`** — меморандумы и договоры: следующий шаг и его дата, ответственный, момент
  последнего движения (V40);
- **контакты организации** — телефон и почта на карточке;
- **решение и вопрос по письму и соглашению** — `target_type` пополняется `letter` и
  `agreement`: письма и соглашения встают строками Пульта, и кнопки у строки те же.

Пороги «спит» и «скорость ответа» заводит сид (`app.seed`), как остальные пороги.

Откат удаляет таблицы, контакты и решения и вопросы по письмам и соглашениям: прежняя
схема их не знает.

Ревизия: 0006_interaction
Предыдущая: 0005_ijro
Создана: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_interaction"
down_revision: str | None = "0005_ijro"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TARGETS = "'project', 'task', 'milestone', 'ijro_assignment', 'letter', 'agreement'"
OLD_TARGETS = "'project', 'task', 'milestone', 'ijro_assignment'"


def _targets(values: str) -> None:
    for table in ("leader_decisions", "leader_questions"):
        name = op.f(f"ck_{table}_target_type_is_known")
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"target_type IN ({values})")


def _stamps() -> list[sa.Column[object]]:
    return [
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.add_column("organizations", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column("organizations", sa.Column("email", sa.String(length=200), nullable=True))

    op.create_table(
        "letters",
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("number", sa.String(length=100), nullable=True),
        sa.Column("sent_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("author_person_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("ijro_assignment_id", sa.UUID(), nullable=True),
        sa.Column("answered_on", sa.Date(), nullable=True),
        sa.Column("reply_number", sa.String(length=100), nullable=True),
        sa.Column("rating", sa.String(length=20), nullable=True),
        *_stamps(),
        sa.CheckConstraint(
            "direction IN ('incoming', 'outgoing')", name=op.f("ck_letters_direction_is_known")
        ),
        sa.CheckConstraint(
            "rating IS NULL OR rating IN ('substance', 'formal', 'off_topic')",
            name=op.f("ck_letters_rating_is_known"),
        ),
        sa.CheckConstraint(
            "rating IS NULL OR (direction = 'outgoing' AND answered_on IS NOT NULL)",
            name=op.f("ck_letters_rating_only_for_received_reply"),
        ),
        sa.CheckConstraint(
            "answered_on IS NULL OR answered_on >= sent_on",
            name=op.f("ck_letters_answer_not_before_letter"),
        ),
        sa.CheckConstraint(
            "project_id IS NULL OR ijro_assignment_id IS NULL",
            name=op.f("ck_letters_one_link_at_most"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_letters_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["author_person_id"],
            ["people.id"],
            name=op.f("fk_letters_author_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_letters_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ijro_assignment_id"],
            ["ijro_assignments.id"],
            name=op.f("fk_letters_ijro_assignment_id_ijro_assignments"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_letters")),
    )
    op.create_index(
        "ix_letters_organization_id_answered_on",
        "letters",
        ["organization_id", "answered_on"],
        unique=False,
    )

    op.create_table(
        "agreements",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("signed_on", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("next_step", sa.Text(), nullable=True),
        sa.Column("next_step_on", sa.Date(), nullable=True),
        sa.Column("responsible_person_id", sa.UUID(), nullable=True),
        sa.Column(
            "moved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_stamps(),
        sa.CheckConstraint(
            "kind IN ('memorandum', 'contract')", name=op.f("ck_agreements_kind_is_known")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_agreements_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["responsible_person_id"],
            ["people.id"],
            name=op.f("fk_agreements_responsible_person_id_people"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agreements")),
    )
    op.create_index(
        "ix_agreements_organization_id", "agreements", ["organization_id"], unique=False
    )

    _targets(TARGETS)


def downgrade() -> None:
    op.execute("DELETE FROM leader_questions WHERE target_type IN ('letter', 'agreement')")
    op.execute("DELETE FROM leader_decisions WHERE target_type IN ('letter', 'agreement')")
    _targets(OLD_TARGETS)

    op.drop_index("ix_agreements_organization_id", table_name="agreements")
    op.drop_table("agreements")
    op.drop_index("ix_letters_organization_id_answered_on", table_name="letters")
    op.drop_table("letters")
    op.drop_column("organizations", "email")
    op.drop_column("organizations", "phone")
