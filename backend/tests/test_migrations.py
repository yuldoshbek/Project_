"""Миграции.

Проверяется то, что ломается молча и обнаруживается в самый неподходящий момент:
расходящиеся головы, неработающий откат, схема, разошедшаяся с моделями.

Alembic запускается настоящей консольной командой в отдельном процессе — тем же способом,
каким его запускают разработчик и CI. Прогон идёт на отдельной базе: `downgrade base` не
должен сносить ничего, что нужно другим тестам.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import asyncpg
import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, UniqueConstraint

from app.repos.base import NAMING_CONVENTION, SCHEMA, Base
from tests.conftest import configured_test_db, dsn, run_alembic

pytestmark = pytest.mark.infra

SCRATCH_DATABASE = f"{configured_test_db()}_migrations"


async def _recreate_scratch_database() -> None:
    admin = await asyncpg.connect(dsn("postgres"))
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DATABASE}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{SCRATCH_DATABASE}"')
    finally:
        await admin.close()


async def _drop_scratch_database() -> None:
    admin = await asyncpg.connect(dsn("postgres"))
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DATABASE}" WITH (FORCE)')
    finally:
        await admin.close()


@pytest.fixture
def clean_database() -> Iterator[str]:
    """Пустая база на один тест.

    Фикстура синхронная намеренно: Alembic запускается в подпроцессе, а внутри него
    env.py открывает собственный цикл событий. Асинхронный тест сюда не годится.
    """
    asyncio.run(_recreate_scratch_database())
    try:
        yield SCRATCH_DATABASE
    finally:
        asyncio.run(_drop_scratch_database())


def test_single_head() -> None:
    """Голова должна быть одна.

    Две головы появляются, когда миграции создаются параллельно в разных ветках, и это
    единственная ошибка процесса, которую нельзя разобрать правкой базы вручную.
    Правило записано в docs/tickets/INDEX.md; здесь оно проверяется.
    """
    result = run_alembic("heads", database=configured_test_db())

    assert result.returncode == 0, result.stderr
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1, f"голов больше одной: {heads}"


def test_upgrade_downgrade_upgrade_on_clean_database(clean_database: str) -> None:
    """Полный цикл на пустой базе.

    Откат проверяется наравне с накатом: миграция без работающего отката — это миграция,
    которую нельзя применить в рабочем контуре.
    """
    up = run_alembic("upgrade", "head", database=clean_database)
    assert up.returncode == 0, up.stderr

    down = run_alembic("downgrade", "base", database=clean_database)
    assert down.returncode == 0, down.stderr

    again = run_alembic("upgrade", "head", database=clean_database)
    assert again.returncode == 0, again.stderr


def test_models_match_migrations(clean_database: str) -> None:
    """Схема и модели не разошлись.

    `alembic check` падает, если по моделям можно сгенерировать непустую миграцию, —
    то есть если кто-то изменил модель и забыл миграцию.

    Проверка идёт на свежей базе, накатанной до головы, а не на той, что подвернулась:
    иначе результат зависел бы от состояния чужой базы и тест то падал бы, то нет.
    """
    assert run_alembic("upgrade", "head", database=clean_database).returncode == 0

    result = run_alembic("check", database=clean_database)

    assert result.returncode == 0, (
        f"модели разошлись со схемой: создайте миграцию\n{result.stdout}\n{result.stderr}"
    )


def test_version_table_lives_in_our_schema(clean_database: str) -> None:
    """Таблица версий — в схеме orbita, а не в public.

    `public` делится с ассистентом SETA (ADR-0001): в общей схеме две системы начали бы
    переписывать номер версии друг другу.
    """
    assert run_alembic("upgrade", "head", database=clean_database).returncode == 0

    async def fetch_schema() -> str | None:
        connection = await asyncpg.connect(dsn(clean_database))
        try:
            value = await connection.fetchval(
                "SELECT table_schema FROM information_schema.tables "
                "WHERE table_name = 'alembic_version'"
            )
        finally:
            await connection.close()
        return str(value) if value is not None else None

    assert asyncio.run(fetch_schema()) == SCHEMA


def test_required_extensions_are_installed(clean_database: str) -> None:
    """После наката расширения на месте — на них опирается поиск и первичные ключи."""
    assert run_alembic("upgrade", "head", database=clean_database).returncode == 0

    async def fetch_extensions() -> set[str]:
        connection = await asyncpg.connect(dsn(clean_database))
        try:
            rows = await connection.fetch("SELECT extname FROM pg_extension")
            return {row["extname"] for row in rows}
        finally:
            await connection.close()

    assert {"pg_trgm", "unaccent", "citext", "pgcrypto"} <= asyncio.run(fetch_extensions())


def test_no_naive_timestamp_columns(clean_database: str) -> None:
    """Ни одной колонки без часового пояса во всей схеме.

    Инвариант CLAUDE.md. Проверять его глазами бесполезно: `Mapped[datetime]` без
    явного `DateTime(timezone=True)` даёт `timestamp without time zone`, и разница не
    видна ни в модели, ни в ревью — она обнаруживается, когда руководитель в поездке
    видит сдвинутые сроки. Один раз это уже случилось при ORB-010.
    """
    assert run_alembic("upgrade", "head", database=clean_database).returncode == 0

    async def fetch_naive_columns() -> list[str]:
        connection = await asyncpg.connect(dsn(clean_database))
        try:
            rows = await connection.fetch(
                "SELECT table_name || '.' || column_name AS column "
                "FROM information_schema.columns "
                "WHERE table_schema = $1 AND data_type = 'timestamp without time zone'",
                SCHEMA,
            )
            return [row["column"] for row in rows]
        finally:
            await connection.close()

    naive = asyncio.run(fetch_naive_columns())
    assert naive == [], f"время без часового пояса: используйте DateTime(timezone=True) в {naive}"


class TestSchemaConventions:
    def test_metadata_is_bound_to_our_schema(self) -> None:
        assert Base.metadata.schema == SCHEMA

    def test_constraints_get_predictable_names(self) -> None:
        """Имена ограничений одинаковы на всех установках.

        Иначе их придумывает PostgreSQL, у каждой установки по-своему, и откат миграции
        падает там, где его никто не проверял.
        """
        metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)
        table = Table(
            "образец",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("код", String, index=True),
            UniqueConstraint("код"),
        )

        assert table.primary_key.name == "pk_образец"
        assert {constraint.name for constraint in table.constraints if constraint.name} >= {
            "pk_образец",
            "uq_образец_код",
        }
        assert {index.name for index in table.indexes} == {"ix_образец_код"}


def test_environment_overrides_dotenv() -> None:
    """Подмена базы через окружение обязана работать.

    На этом стоят и тесты миграций, и запуск в рабочем контуре, где файла .env нет
    вовсе. Если бы окружение проигрывало файлу, все проверки выше молча шли бы не по
    той базе — и ничего бы не проверяли.
    """
    # Имя латиницей намеренно: сообщение об ошибке приходит из дочернего процесса,
    # и кириллица в нём на Windows искажается кодировкой консоли.
    missing = "orbita_no_such_database"

    result = run_alembic("current", database=missing)

    assert result.returncode != 0
    assert missing in result.stderr, (
        "alembic подключился не к той базе — окружение не перекрыло .env"
    )
