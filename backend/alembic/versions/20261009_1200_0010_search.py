"""Поиск по всем разделам

Поиск по части названия или номера (блок 4, ТЗ 6, V19) — `LIKE '%…%'` по свёрнутому
тексту. Замер 09.10.2026 на объёмах ТЗ 9 (500 проектов, 5 000 задач, 2 000 поручений,
5 000 писем) без индексов: медиана 150–200 мс, худший запрос 376 мс при норме ТЗ «ответ
API меньше 300 мс». Поэтому:

- **`search_fold(text)`** — свёртка текста для поиска: нижний регистр и один вид апострофа
  узбекской латиницы (`app.domain.search.normalize` делает то же со строкой запроса).
  Функция, а не выражение в запросе: индекс по выражению база берёт, только если запрос
  повторяет выражение буква в букву, а с функцией это одно имя;
- **триграммные индексы** `ix_search_*` по `search_fold(столбца)` на каждом столбце, где
  ищет поиск, — `pg_trgm` стоит в базе с первой миграции.

Ревизия: 0010_search
Предыдущая: 0009_ideas
Создана: 2026-10-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_search"
down_revision: str | None = "0009_ideas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Апострофы узбекской латиницы ʻ ʼ ’ ‘ ` — к одному простому. Те же знаки, что
# `app.domain.search.APOSTROPHES`: миграция не импортирует код приложения, чтобы не
# меняться вместе с ним.
FOLD_SQL = """
CREATE FUNCTION search_fold(value text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT translate(lower(value), 'ʻʼ’‘`', '''''''''''') $$
"""

COLUMNS = (
    ("projects", "title"),
    ("projects", "code"),
    ("tasks", "title"),
    ("tasks", "code"),
    ("ijro_assignments", "content"),
    ("ijro_assignments", "code"),
    ("letters", "subject"),
    ("letters", "number"),
    ("organizations", "name"),
    ("organizations", "short_name"),
    ("agreements", "title"),
    ("ideas", "text"),
    ("preparations", "title"),
)


def upgrade() -> None:
    op.execute(FOLD_SQL)
    for table, column in COLUMNS:
        op.execute(
            f"CREATE INDEX ix_search_{table}_{column} ON {table} "
            f"USING gin (search_fold({column}) gin_trgm_ops)"
        )


def downgrade() -> None:
    for table, column in COLUMNS:
        op.execute(f"DROP INDEX IF EXISTS ix_search_{table}_{column}")
    op.execute("DROP FUNCTION IF EXISTS search_fold(text)")
