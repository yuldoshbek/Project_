"""Создание приложения.

Здесь собирается всё вместе: настройки, логи, подключение к базе, обработчики ошибок,
роутеры. Больше ничего: логика живёт в сервисах, запросы — в репозиториях.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.router import api_router
from app.api.routes import health
from app.observability import (
    RequestContextMiddleware,
    configure_logging,
    route_library_logs,
)
from app.repos.database import dispose_database, init_database
from app.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.use_json_logs)
    logger = structlog.get_logger(__name__)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # uvicorn настраивает свои логи после импорта модуля, поэтому забирать их
        # в общий формат нужно здесь, на старте, а не только при настройке.
        route_library_logs()
        init_database(settings)
        logger.info("application_started", env=settings.env)
        try:
            yield
        finally:
            await dispose_database()
            logger.info("application_stopped")

    app = FastAPI(
        title="ORBITA",
        description=(
            "Система управления проектами и задачами Агентства «Ўзбеккосмос». "
            "Пользователей двое: помощник вносит данные, руководитель смотрит и решает."
        ),
        version="0.1.0",
        lifespan=lifespan,
        # Схема API нужна и в рабочем контуре: по ней собирается клиент интерфейса.
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # Настройки привязаны к экземпляру приложения: роутеры берут их отсюда, а не из
    # кешированного чтения окружения. Иначе create_app(settings) даёт приложение,
    # часть которого работает с переданными настройками, а часть — с чужими.
    app.state.settings = settings

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    # Проверки состояния версией не закрываются: их опрашивает инфраструктура,
    # а не интерфейс, и путь не должен меняться вместе с версией API.
    app.include_router(health.router)
    app.include_router(api_router)

    return app


app = create_app()
