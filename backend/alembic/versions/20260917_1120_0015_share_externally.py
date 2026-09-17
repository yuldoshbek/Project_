"""Гриф снят: `projects.classification` становится `projects.share_externally`

Заказчик 16.09 снял безопасность внутри системы дословно: службы безопасности нет,
утечки нет, пользователей двое, и оба видят всё. Половина
[ADR-0007](../../../docs/adr/ADR-0007-restricted-data.md) умерла ещё раньше, вместе
с ролями и таблицей участников ([ADR-0011](../../../docs/adr/ADR-0011-two-user-scope.md)):
делить между двумя людьми, которые оба видят всё, нечего.

Вторая половина не умерла, а выросла. Точек выхода наружу стало пять — Google-календарь,
SETA, Telegram через её бота, экспорт, внешняя модель, — и вопрос «можно ли это
показывать наружу» задал сам заказчик. Поэтому колонка не удаляется, а переименовывается
по смыслу: не «секретно ли это», а «показывать ли наружу»
([ADR-0024](../../../docs/adr/ADR-0024-share-externally.md)).

Перенос значения — выражением `classification <> 'restricted'`: закрытый проект наружу не
уходил и не уходит, остальные уходят. Обратный перенос в откате точен ровно настолько же,
потому что значений было два и они взаимно однозначны — третьего уровня в колонке
никогда не было.

Ограничение переписывать не приходится: его и не было. Миграция
`20260910_1645_0006_projects.py:36` объявляет `sa.String(length=20)` без CHECK, а
допустимые значения держал только Python — то есть до сегодняшнего дня в колонку можно
было записать любое слово, и база не возразила бы. Булево значение эту дыру закрывает
типом, а не проверкой.

Значение по умолчанию — `true`, «показывать». Это сознательный выбор ADR-0024 и он же
там назван плохим последствием: пока в форме создания проекта нет переключателя, каждый
новый проект уходит наружу молча. Переключатель приносит ORB-086 в этой же волне.

Ревизия: 0015_share_externally
Предыдущая: 0014_seta_interop
Создана: 2026-09-17 11:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_share_externally"
down_revision: str | None = "0014_seta_interop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Колонка добавляется, заполняется и лишь потом становится NOT NULL: на непустой
    # таблице `add_column` с NOT NULL без умолчания отказывает, а умолчание, проставленное
    # до переноса, сделало бы «показывать наружу» и для закрытых проектов.
    op.add_column("projects", sa.Column("share_externally", sa.Boolean(), nullable=True))
    op.execute("UPDATE projects SET share_externally = (classification <> 'restricted')")
    op.alter_column(
        "projects",
        "share_externally",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.true(),
    )

    op.drop_column("projects", "classification")


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция, которую
    # нельзя применить в рабочем контуре.
    op.add_column("projects", sa.Column("classification", sa.String(length=20), nullable=True))
    op.execute(
        "UPDATE projects SET classification = "
        "CASE WHEN share_externally THEN 'internal' ELSE 'restricted' END"
    )
    op.alter_column(
        "projects",
        "classification",
        existing_type=sa.String(length=20),
        nullable=False,
    )

    op.drop_column("projects", "share_externally")
