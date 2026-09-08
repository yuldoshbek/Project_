"""Проверки состояния.

Две разные проверки, и путать их нельзя.

`/health` — живость: процесс отвечает. Не трогает ни базу, ни Redis. Если бы трогал,
недоступность базы приводила бы к перезапуску приложения, которое исправно, — и
перезапускалось бы оно по кругу, пока база не вернётся.

`/ready` — готовность обслуживать запросы: база и Redis отвечают. Отдаёт 503, если нет,
и называет, что именно не отвечает: без этого разбирательство начинается с угадывания.
"""

from __future__ import annotations

import asyncio
from typing import Literal

import structlog
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.adapters.redis_client import create_redis
from app.api.deps import SettingsDep
from app.repos.database import get_engine

router = APIRouter(tags=["служебные"])
logger = structlog.get_logger(__name__)

# Проверка готовности не должна висеть: балансировщик ждёт ответа, а не правды любой ценой.
CHECK_TIMEOUT_SECONDS = 3.0


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


@router.get("/health", response_model=HealthResponse, summary="Живость процесса")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


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


async def check_redis(url: str) -> str:
    client = create_redis(url)
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            await client.ping()
    except Exception as error:
        logger.warning("redis_check_failed", error=str(error))
        return f"недоступен: {type(error).__name__}"
    finally:
        await client.aclose()
    return "ok"


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Готовность обслуживать запросы",
    responses={503: {"description": "Одна из зависимостей недоступна"}},
)
async def ready(settings: SettingsDep, response: Response) -> ReadinessResponse:
    database, redis = await asyncio.gather(
        check_database(),
        check_redis(settings.redis_url),
    )
    checks = {"database": database, "redis": redis}
    is_ready = all(value == "ok" for value in checks.values())

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning("not_ready", checks=checks)

    return ReadinessResponse(status="ready" if is_ready else "not_ready", checks=checks)
