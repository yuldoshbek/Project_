"""Проверки состояния.

Две разные проверки, и путать их нельзя.

`/api/health` — живость: процесс отвечает и говорит, какой коммит в нём выложен. Базу не
трогает. Если бы трогал, недоступность базы приводила бы к перезапуску исправного
приложения — и перезапускалось бы оно по кругу, пока база не вернётся.

`/api/ready` — готовность обслуживать запросы: база отвечает. Отдаёт 503, если нет, и
называет, что именно не отвечает: без этого разбирательство начинается с угадывания.

Путь начинается с `/api` не для красоты: интерфейс стоит на Netlify и проксирует на API
только `/api/*` (ADR-0028). Проверка, доступная мимо прокси, проверяла бы не тот путь,
которым ходят люди.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Literal

import structlog
from fastapi import Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import SettingsDep
from app.api.transaction import transactional_router
from app.repos.database import get_engine

router = transactional_router(prefix="/api", tags=["служебные"])
logger = structlog.get_logger(__name__)

# Проверка готовности не должна висеть: тот, кто её опрашивает, ждёт ответа, а не правды
# любой ценой.
CHECK_TIMEOUT_SECONDS = 3.0


class HealthResponse(BaseModel):
    status: Literal["ok"]
    commit: str
    """Коммит выложенной сборки. Выкладка сверяет его с тем, что выкладывала: иначе
    успешной выкладкой считается кеш прежней сборки (deploy.yml)."""
    env: str
    time: datetime


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


@router.get("/health", response_model=HealthResponse, summary="Живость процесса")
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        commit=settings.commit,
        env=settings.env,
        time=datetime.now(UTC),
    )


async def check_database() -> str:
    # Ловится любое исключение: задача проверки — доложить о состоянии, а не упасть.
    # Тип ошибки в ответе есть, подробности уходят в лог.
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS), get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as error:
        logger.warning("database_check_failed", error=str(error))
        return f"недоступна: {type(error).__name__}"
    return "ok"


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Готовность обслуживать запросы",
    responses={503: {"description": "База недоступна"}},
)
async def ready(response: Response) -> ReadinessResponse:
    checks = {"database": await check_database()}
    is_ready = all(value == "ok" for value in checks.values())

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning("not_ready", checks=checks)

    return ReadinessResponse(status="ready" if is_ready else "not_ready", checks=checks)
