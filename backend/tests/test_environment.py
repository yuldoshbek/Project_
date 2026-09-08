"""Проверка локального окружения (ORB-002).

Тесты отвечают на один вопрос: то ли окружение подняли, что нужно приложению. Ошибка
здесь дешевле любой другой — она видна до того, как разработчик начал искать причину
в собственном коде.
"""

from __future__ import annotations

import asyncpg
import pytest
import redis.asyncio as aioredis

from tests.conftest import REQUIRED_EXTENSIONS, configured_test_db, dev_database, redis_url

pytestmark = pytest.mark.infra


def test_test_database_differs_from_dev() -> None:
    """Разные базы для разработки и тестов — иначе прогон тестов затрёт рабочие данные."""
    assert configured_test_db() != dev_database()


async def test_postgres_version_is_16_or_newer(db: asyncpg.Connection) -> None:
    """PostgreSQL 16 — требование ADR-0002, ниже версией часть возможностей недоступна."""
    version: int = await db.fetchval("SHOW server_version_num")
    assert int(version) >= 160000, f"нужен PostgreSQL 16 или новее, найден {version}"


@pytest.mark.parametrize("extension", REQUIRED_EXTENSIONS)
async def test_required_extension_installed(db: asyncpg.Connection, extension: str) -> None:
    """Расширения нужны поиску (ADR-0006) и первичным ключам."""
    installed = await db.fetchval(
        "SELECT 1 FROM pg_extension WHERE extname = $1",
        extension,
    )
    assert installed == 1, f"расширение {extension} не включено в тестовой базе"


async def test_search_normalization_building_blocks(db: asyncpg.Connection) -> None:
    """Кирпичи будущего поиска работают: unaccent снимает диакритику, trigram считает похожесть.

    Полная нормализация с транслитерацией узбекской латиницы — тикет ORB-033.
    Здесь проверяется только то, что расширения действительно рабочие, а не просто
    числятся в pg_extension.
    """
    assert await db.fetchval("SELECT unaccent('Oʻzbekiston')") is not None
    similarity: float = await db.fetchval("SELECT similarity('kosmik', 'kosmiq')")
    assert 0.0 < similarity < 1.0


async def test_redis_reachable() -> None:
    """Redis нужен фоновым задачам: напоминаниям, эскалации, отчётам (ADR-0008)."""
    client = aioredis.from_url(redis_url())
    try:
        assert await client.ping() is True
    except OSError as error:
        pytest.fail(
            f"нет подключения к Redis по адресу {redis_url()}: {error}. "
            "Поднимите окружение: make up"
        )
    finally:
        await client.aclose()
