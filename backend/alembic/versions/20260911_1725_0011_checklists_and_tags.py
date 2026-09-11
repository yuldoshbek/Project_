"""Чек-листы и теги задач

Три таблицы вместо двух полей у задачи, и это не усложнение ради нормальной формы.

Список подзадач в текстовом поле нельзя отметить — а отметка и есть весь смысл чек-листа.
Теги строкой через запятую нельзя собрать: вопрос «какие задачи помечены этим тегом» —
тот самый, ради которого теги заводятся (ТЗ 6.2), — превращается в поиск по подстроке,
находящий «ДЗЗ» внутри «ДЗЗ-2».

Имя тега — `citext`: «ДЗЗ» и «дзз» должны быть одним тегом, и обеспечивает это тип
столбца, а не проверка в коде. Проверку обходит первый же импорт, тип — никто. Расширение
заведено ещё базовой миграцией ради адреса пользователя.

Прогресс чек-листа здесь не хранится: он считается из самих пунктов на выдаче — по той же
причине, по которой не хранится просрочка задачи (ADR-0004). Столбец «выполнено N из M»
разошёлся бы с пунктами молча, и спорить с ним было бы нечем.

Ревизия: 0011_checklists_and_tags
Предыдущая: 0010_impediment
Создана: 2026-09-11 17:25:49.547317
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_checklists_and_tags"
down_revision: str | None = "0010_impediment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_index("ix_task_tags_tag_id", table_name="task_tags")
    op.drop_table("task_tags")
    op.drop_index("ix_task_checklist_items_task_id_sort_order", table_name="task_checklist_items")
    op.drop_table("task_checklist_items")
    op.drop_table("tags")
