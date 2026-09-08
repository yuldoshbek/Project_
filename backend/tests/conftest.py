"""Общие приспособления для тестов.

Главное правило здесь — тесты работают с отдельной базой и никогда не трогают базу
разработки. Проверка вынесена в `guard_separate_database`: она срабатывает раньше любого
подключения, потому что цена ошибки — затёртые данные разработчика.

Имена функций-помощников намеренно не начинаются с `test_`: иначе pytest собирает их как
тесты и ругается, что они возвращают значение.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from dotenv import load_dotenv
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.main import create_app
from app.repos.database import dispose_database, init_database
from app.settings import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Значения по умолчанию совпадают с docker-compose.yml: после `make up` тесты работают
# без дополнительной настройки. Файл .env, если он есть, перекрывает умолчания.
load_dotenv(REPO_ROOT / ".env", override=False)

REQUIRED_EXTENSIONS = ("pg_trgm", "unaccent", "citext", "pgcrypto")


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


def dev_database() -> str:
    return _env("ORBITA_DB_NAME", "orbita")


def configured_test_db() -> str:
    return _env("ORBITA_TEST_DB", "orbita_test")


def dsn(database: str) -> str:
    user = _env("ORBITA_DB_USER", "orbita")
    password = _env("ORBITA_DB_PASSWORD", "orbita")
    host = _env("ORBITA_DB_HOST", "localhost")
    port = _env("ORBITA_DB_PORT", "55432")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def redis_url() -> str:
    return _env("ORBITA_REDIS_URL", "redis://localhost:56379/0")


@pytest.fixture(scope="session", autouse=True)
def guard_separate_database() -> None:
    """Не даёт тестам работать с базой разработки."""
    if configured_test_db() == dev_database():
        pytest.exit(
            f"ORBITA_TEST_DB совпадает с ORBITA_DB_NAME ({configured_test_db()!r}). "
            "Тесты затрут данные разработки — задайте разные имена в .env.",
            returncode=2,
        )


@pytest.fixture(scope="session")
def test_dsn(guard_separate_database: None) -> str:
    return dsn(configured_test_db())


@pytest.fixture
async def db(test_dsn: str) -> AsyncIterator[asyncpg.Connection]:
    """Подключение к тестовой базе.

    Если базы нет — падаем с внятным текстом, а не пропускаем тест: молчаливый skip
    выглядит как успех и прячет неподнятое окружение.
    """
    try:
        connection = await asyncpg.connect(test_dsn)
    except (OSError, asyncpg.PostgresError) as error:
        pytest.fail(
            f"нет подключения к тестовой базе {configured_test_db()!r}: {error}. "
            "Поднимите окружение: make up (в Windows .\\make.ps1 up)"
        )

    # В окружении CI база создаётся сервис-контейнером без init-скриптов, поэтому
    # расширения включаем здесь. Операция идемпотентна.
    for extension in REQUIRED_EXTENSIONS:
        await connection.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension}"')

    try:
        yield connection
    finally:
        await connection.close()


# --------------------------------------------------------------------------
# Приложение
# --------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    """Настройки для тестов.

    Собираются явно, а не читаются из окружения: тесты не должны зависеть от того, есть
    ли на машине файл .env и что в нём написано. Единственное, что берётся из окружения, —
    адреса поднятых сервисов.
    """
    return Settings(
        env="test",
        secret_key=SecretStr("test-secret-not-for-production"),
        db_host=_env("ORBITA_DB_HOST", "localhost"),
        db_port=int(_env("ORBITA_DB_PORT", "55432")),
        db_name=configured_test_db(),
        db_user=_env("ORBITA_DB_USER", "orbita"),
        db_password=SecretStr(_env("ORBITA_DB_PASSWORD", "orbita")),
        redis_url=redis_url(),
        log_json=True,
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    """Приложение с поднятым подключением к базе.

    `ASGITransport` не выполняет lifespan, поэтому подключение создаётся здесь вручную.
    Что сам lifespan отрабатывает, проверяется отдельно в `test_lifespan_opens_database`.
    """
    application = create_app(settings)
    init_database(settings)
    try:
        yield application
    finally:
        await dispose_database()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    # raise_app_exceptions=False: Starlette возвращает ответ обработчика и следом
    # пробрасывает исключение дальше, чтобы сервер его записал. В тесте нам нужен
    # именно ответ — иначе проверить формат ошибки 500 невозможно.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
