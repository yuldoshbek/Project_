"""Общие приспособления для тестов.

Главное правило здесь — тесты работают с отдельной базой и никогда не трогают базу
разработки. Проверка вынесена в `guard_separate_database`: она срабатывает раньше любого
подключения, потому что цена ошибки — затёртые данные разработчика.

Имена функций-помощников намеренно не начинаются с `test_`: иначе pytest собирает их как
тесты и ругается, что они возвращают значение.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from dotenv import load_dotenv
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_session
from app.main import create_app
from app.repos.database import dispose_database, init_database
from app.seed import seed
from app.settings import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_ROOT = Path(__file__).resolve().parent.parent

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
    host = _env("ORBITA_DB_HOST", "127.0.0.1")
    port = _env("ORBITA_DB_PORT", "55432")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def redis_url() -> str:
    return _env("ORBITA_REDIS_URL", "redis://127.0.0.1:56379/0")


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


def build_settings() -> Settings:
    """Настройки для тестов.

    Собираются явно, а не читаются из окружения: тесты не должны зависеть от того, есть
    ли на машине файл .env и что в нём написано. Единственное, что берётся из окружения, —
    адреса поднятых сервисов.
    """
    return Settings(
        env="test",
        secret_key=SecretStr("test-secret-not-for-production"),
        db_host=_env("ORBITA_DB_HOST", "127.0.0.1"),
        db_port=int(_env("ORBITA_DB_PORT", "55432")),
        db_name=configured_test_db(),
        db_user=_env("ORBITA_DB_USER", "orbita"),
        db_password=SecretStr(_env("ORBITA_DB_PASSWORD", "orbita")),
        redis_url=redis_url(),
        log_json=True,
    )


@pytest.fixture
def settings() -> Settings:
    return build_settings()


@pytest.fixture(scope="session")
def settings_for_session() -> Settings:
    """Те же настройки для приспособлений уровня прогона."""
    return build_settings()


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


# --------------------------------------------------------------------------
# Схема и данные
# --------------------------------------------------------------------------


def alembic_executable() -> Path:
    bin_dir = Path(sys.executable).parent
    for name in ("alembic.exe", "alembic"):
        candidate = bin_dir / name
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"alembic не найден в {bin_dir}; выполните uv sync --all-groups")


def run_alembic(*args: str, database: str) -> subprocess.CompletedProcess[str]:
    """Запускает alembic на указанной базе.

    Настройки читаются из окружения и перекрывают файл .env, поэтому подменять базу
    достаточно переменными — так же, как это делается в рабочем контуре.
    """
    env = {
        **os.environ,
        "ORBITA_DB_NAME": database,
        "ORBITA_SECRET_KEY": "test-secret-not-for-production",
        "ORBITA_ENV": "test",
    }
    return subprocess.run(  # noqa: S603
        [str(alembic_executable()), *args],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


@pytest.fixture(scope="session")
def migrated_database(guard_separate_database: None, settings_for_session: Settings) -> str:
    """Тестовая база: схема накатана, справочники наполнены. Один раз за прогон.

    Наполнение вынесено сюда, а не в каждый тест, по измеренной причине: сиды — это
    два-три десятка отдельных обращений к базе, и через проброс портов Docker они
    стоили 2,3 секунды на каждый тест. Медленный набор тестов перестают запускать,
    и это опаснее любой экономии на чистоте.

    Изоляция от этого не страдает: каждый тест работает во внешней транзакции,
    которая откатывается (см. `session`).
    """
    database = configured_test_db()
    result = run_alembic("upgrade", "head", database=database)
    if result.returncode != 0:
        pytest.fail(f"не удалось накатить схему на {database}: {result.stdout} {result.stderr}")

    asyncio.run(_seed_once(settings_for_session))
    return database


async def _seed_once(settings: Settings) -> None:
    engine = create_async_engine(settings.database_url)
    try:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as active:
            await seed(active)
            await active.commit()
    finally:
        await engine.dispose()


@pytest.fixture
async def session(settings: Settings, migrated_database: str) -> AsyncIterator[AsyncSession]:
    """Сессия, все изменения которой откатываются после теста.

    В базе уже есть справочники раздела 7 ТЗ и две учётные записи: они наполняются
    один раз за прогон (`migrated_database`). Пустой схемы у тестов нет — и не нужно:
    система без справочников нерабочая, проверять её в таком виде бессмысленно.

    Сессия работает внутри внешней транзакции, а та откатывается: тесты не оставляют
    следов друг для друга, и порядок их выполнения перестаёт влиять на результат. Это
    важнее скорости — при общей базе один забытый `commit` делает соседний тест
    непредсказуемым.
    """
    engine = create_async_engine(settings.database_url, poolclass=None)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

    async with factory() as active:
        try:
            yield active
        finally:
            await active.close()
            await transaction.rollback()
            await connection.close()
            await engine.dispose()


@pytest.fixture
async def api(app: FastAPI, session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Клиент API, работающий в той же откатываемой транзакции, что и тест.

    Без подмены зависимости роутеры открыли бы собственную сессию и своё соединение —
    и не увидели бы данных, подготовленных тестом.
    """

    async def use_test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = use_test_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client
    finally:
        app.dependency_overrides.clear()
