"""Стенд сценариев Playwright на машине разработчика: своя база и свой API.

Отдельно от `make dev` по двум наблюдённым причинам. Сценарии выпускают ссылки доступа, а
перевыпуск закрывает прежние сессии роли (ADR-0029): прогон на базе разработки выбивал
разработчика из его же вкладки — «Откройте ORBITA по своей личной ссылке» после каждого
`make e2e`. И прогон расходовал вымышленные данные — контрольные отметки Ижро, «что если»,
идеи из Захвата: через десяток прогонов сценарии падали не от кода. Поэтому база стенда
перед каждым прогоном пересоздаётся с нуля, как в CI, и API поднимается на ней на своём
порту, не мешая окну разработки.

Запускает Playwright (`frontend/playwright.config.ts`, `webServer`), а не человек: база и
порт приходят оттуда переменными окружения. Пересоздаётся только база с именем `*_e2e`,
собранная из частей `ORBITA_DB_*`: строку `ORBITA_DATABASE_URL` облака или сервера сюда не
подставить даже по ошибке.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys

import asyncpg
import uvicorn

from app.settings import Settings, get_settings

SUFFIX = "_e2e"
EXTENSIONS = ("pg_trgm", "unaccent", "pgcrypto")
"""Ставятся здесь же, как init-скрипт контейнера ставит их базе разработки: миграция
`0001_foundation` ставит их сама, только если хватает прав."""


def _refuse_foreign(settings: Settings) -> None:
    if settings.env == "production" or settings.database_url:
        raise SystemExit(
            "стенд e2e пересоздаёт базу целиком: ORBITA_DATABASE_URL должен быть пуст, "
            "а контур — не рабочий"
        )
    if not settings.db_name.endswith(SUFFIX):
        raise SystemExit(
            f"стенд e2e пересоздаёт только базу с именем *{SUFFIX}, а не {settings.db_name!r}"
        )


async def _recreate(settings: Settings) -> None:
    common = {
        "host": settings.db_host,
        "port": settings.db_port,
        "user": settings.db_user,
        "password": settings.db_password.get_secret_value(),
    }
    server = await asyncpg.connect(database="postgres", **common)
    try:
        # FORCE — висящие соединения прошлого прогона (API, убитый вместе с Playwright)
        # иначе не дают удалить базу.
        await server.execute(f'DROP DATABASE IF EXISTS "{settings.db_name}" WITH (FORCE)')
        await server.execute(f'CREATE DATABASE "{settings.db_name}"')
    finally:
        await server.close()
    fresh = await asyncpg.connect(database=settings.db_name, **common)
    try:
        for name in EXTENSIONS:
            await fresh.execute(f'CREATE EXTENSION IF NOT EXISTS "{name}"')
    finally:
        await fresh.close()


def _step(*args: str) -> None:
    # S603: интерпретатор — sys.executable этого окружения, аргументы — строки из кода ниже.
    subprocess.run([sys.executable, *args], check=True)  # noqa: S603


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8001)
    port = parser.parse_args().port

    settings = get_settings()
    _refuse_foreign(settings)
    asyncio.run(_recreate(settings))
    # Тем же порядком, что шаг «Схема и справочники» в CI: миграции, справочники, демо.
    _step("-m", "alembic", "upgrade", "head")
    _step("-m", "app.seed")
    _step("-m", "app.demo")
    # Журнал обращений — по `ORBITA_E2E_STAND_LOG`: разбор падения, а не каждый прогон.
    level = "info" if os.environ.get("ORBITA_E2E_STAND_LOG") else "warning"
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level=level)


if __name__ == "__main__":
    main()
