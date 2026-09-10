"""Строка «что мешает» у проекта

Одно текстовое поле и дата его обновления — всё, что система знает о рисках
([ADR-0016](../../../docs/adr/ADR-0016-risks-signals-not-register.md)). Реестра рисков с
вероятностью, влиянием и планом реагирования нет и не будет: он требует регулярного
пересмотра руками, которого при одном вносящем человеке не случится, и через квартал
превращается в кладбище записей, которым никто не верит.

Дату ставит система при изменении текста. Дата, которой можно управлять, перестаёт
отвечать на вопрос «насколько это свежо» — а весь смысл поля в свежести.

Ревизия: 0010_impediment
Предыдущая: 0009_project_partners
Создана: 2026-09-10 20:07:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_impediment"
down_revision: str | None = "0009_project_partners"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("impediment", sa.Text(), nullable=True))
    op.add_column(
        "projects", sa.Column("impediment_updated_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_column("projects", "impediment_updated_at")
    op.drop_column("projects", "impediment")
