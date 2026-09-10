"""Регламентные задания.

Каждое обязано быть **идемпотентным**: повторный запуск на тех же данных не производит
второго действия (CLAUDE.md, инвариант 6). Это не пожелание к аккуратности — воркер
перезапускается при выкладке, задание может выполниться дважды, и без идемпотентности
второй прогон шлёт второе напоминание.

Здесь пока одно задание. Напоминания и эскалация приходят с ORB-038 и ORB-039, снимки
состояния — с ORB-063, отчёты — с ORB-044: каждое заводит своё, а не дописывает сюда
заранее пустые заглушки.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import RefreshToken
from app.workers.context import job, job_scope

logger = structlog.get_logger(__name__)

REVOKED_RETENTION = timedelta(days=30)
"""Сколько держать отозванный токен после отзыва.

Не ноль: по отозванным токенам разбирают, откуда взялась чужая сессия, и месяц — тот срок,
за который такой разбор случается. Дальше запись превращается в мусор, который растёт.
"""


async def purge_stale_sessions(ctx: dict[str, Any]) -> int:
    """Убирает истёкшие и давно отозванные токены обновления.

    Идемпотентно по устройству: удаление того, чего уже нет, — не действие. Второй прогон
    подряд удалит ноль записей и ничего не сообщит.

    Без этого таблица растёт вечно: у двух пользователей это медленно, но «медленно» —
    не «никогда», а чистить её потом руками будет некому.
    """
    async with job_scope("purge_stale_sessions", job_id=ctx.get("job_id")) as session:
        return await purge_stale_sessions_once(session, now=datetime.now(UTC))


async def purge_stale_sessions_once(session: AsyncSession, *, now: datetime) -> int:
    """Само действие, отдельно от обвязки задания.

    Отдельно — чтобы проверять его сессией теста, а не поднятым воркером: тест,
    требующий воркера, проверяет заодно и ARQ, и Redis, и падает от любой их икоты.
    """
    condition = or_(
        RefreshToken.expires_at < now,
        RefreshToken.revoked_at.is_not(None) & (RefreshToken.revoked_at < now - REVOKED_RETENTION),
    )

    doomed = list(await session.scalars(select(RefreshToken.id).where(condition)))
    if not doomed:
        logger.info("purge_stale_sessions_nothing_to_do")
        return 0

    await session.execute(delete(RefreshToken).where(RefreshToken.id.in_(doomed)))
    await session.flush()

    logger.info("purge_stale_sessions_done", removed=len(doomed))
    return len(doomed)


purge_stale_sessions_job = job(purge_stale_sessions)
