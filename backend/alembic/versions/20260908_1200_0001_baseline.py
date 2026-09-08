"""Основание схемы: расширения PostgreSQL

Первая миграция не создаёт таблиц — предметные сущности появятся следующими тикетами.
Она проверяет, что база готова: без `pg_trgm` и `unaccent` не соберётся поиск на трёх
письменностях (ADR-0006), без `pgcrypto` не выдаются первичные ключи, без `citext` не
работает регистронезависимый адрес почты.

Смысл проверки — в моменте, когда она срабатывает. Без неё отсутствие расширения
обнаружится через несколько тикетов, при создании GIN-индекса, и сообщение будет о чём
угодно, только не о причине.

Саму схему `orbita` создаёт `env.py` до запуска миграций: Alembic должен где-то завести
таблицу версий, а она уже живёт в этой схеме.

Ревизия: 0001_baseline
Предыдущая: нет
Создана: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REQUIRED_EXTENSIONS: tuple[tuple[str, str], ...] = (
    ("pg_trgm", "поиск с опечатками и частичным вводом (ADR-0006)"),
    ("unaccent", "снятие диакритики при нормализации поискового текста (ADR-0006)"),
    ("citext", "регистронезависимый адрес электронной почты"),
    ("pgcrypto", "gen_random_uuid для первичных ключей"),
)


def upgrade() -> None:
    connection = op.get_bind()

    for name, purpose in REQUIRED_EXTENSIONS:
        installed = connection.scalar(
            sa.text("SELECT 1 FROM pg_extension WHERE extname = :name"),
            {"name": name},
        )
        if installed:
            continue

        # В окружении разработки расширения включает init-скрипт контейнера, в рабочем
        # контуре — администратор базы: CREATE EXTENSION требует прав суперпользователя,
        # которых у приложения быть не должно. Попытка всё же делается: там, где прав
        # хватает, миграция проходит сама.
        try:
            connection.exec_driver_sql(f'CREATE EXTENSION IF NOT EXISTS "{name}"')
        except sa.exc.DBAPIError as error:
            raise RuntimeError(
                f"расширение PostgreSQL {name!r} не установлено и не может быть создано "
                f"приложением. Нужно для: {purpose}. "
                f"Попросите администратора базы выполнить: "
                f'CREATE EXTENSION IF NOT EXISTS "{name}";'
            ) from error


def downgrade() -> None:
    # Расширения намеренно не удаляются. База делится с ассистентом SETA (ADR-0001):
    # `DROP EXTENSION` снёс бы вместе с расширением и всё, что от него зависит у соседа.
    # Откат этой миграции возвращает базу к состоянию «есть пустая схема orbita».
    pass
