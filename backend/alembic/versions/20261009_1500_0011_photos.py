"""Фото из Захвата

Захват кладёт фото к тому, что завёл (блок 4, ТЗ 7, V18): к задаче, к идее или к записи во
входящих — письмо и мероприятие ждут там своих разделов (V17). Таблица файлов уже есть
(0008_files) — расширяется только набор владельцев в проверке `owner_type`.

Ревизия: 0011_photos
Предыдущая: 0010_search
Создана: 2026-10-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011_photos"
down_revision: str | None = "0010_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_stored_files_owner_type_is_known"
"""Имя полное — поэтому в вызовах оно идёт через `op.f`, иначе соглашение об именах добавило
бы префикс ck_ второй раз. `op.f` работает только внутри миграции, не при чтении модуля."""


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "stored_files", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT),
        "stored_files",
        "owner_type IN ('presentation_version', 'task', 'idea', 'capture')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM stored_files WHERE owner_type <> 'presentation_version'")
    op.drop_constraint(op.f(CONSTRAINT), "stored_files", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), "stored_files", "owner_type IN ('presentation_version')"
    )
