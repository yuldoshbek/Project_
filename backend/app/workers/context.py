"""Обвязка фонового задания: кто действует, что писать в лог, где брать сессию.

Три вещи, которые задание не должно делать само, потому что однажды забудет.

**Кто действует.** Изменение, сделанное по расписанию, обязано быть подписано заданием, а
не последним вошедшим человеком: иначе в журнале эскалация и автосоздание повторяющейся
задачи выглядят как чьё-то решение ([ADR-0010](../../../docs/adr/ADR-0010-audit-log.md)).

**Что писать в лог.** У каждого прогона свой идентификатор, тот же, что попадёт в записи
журнала изменений. По нему находится и то, что задание изменило, и то, что при этом
происходило внутри — критерий приёмки ORB-036 требует именно этого.

**Повторные попытки.** Задание падает не потому, что оно неверное, а потому, что база
перезагружалась или Telegram ответил пятисоткой. Повтор с растущей задержкой переживает
такое; повтор без задержки превращает единичный сбой в сотню строк в логе.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from functools import wraps
from typing import Any

import structlog
from arq import Retry
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit import ActorKind
from app.observability import normalize_request_id
from app.repos.database import session_scope
from app.services.audit import Actor, set_actor

logger = structlog.get_logger(__name__)

MAX_TRIES = 3
"""Три попытки, а не бесконечность.

Задание, падающее четвёртый раз подряд, падает не от невезения: дальше повторять — значит
прятать поломку за шумом и держать очередь занятой.
"""

FIRST_RETRY_DELAY = timedelta(seconds=30)
"""Задержка первой повторной попытки. Дальше удваивается."""


def retry_delay(job_try: int) -> timedelta:
    """Экспоненциальная задержка: 30 секунд, минута, две.

    Постоянная задержка не помогает: если внешняя система лежит, она лежит дольше, чем
    интервал, и повторы просто пересчитывают её недоступность.
    """
    # Сдвиг, а не возведение в степень: `2 ** n` для типизатора может дать число с
    # плавающей точкой, и умножение на него перестаёт быть длительностью.
    return FIRST_RETRY_DELAY * (1 << (job_try - 1))


@asynccontextmanager
async def job_context(name: str, *, job_id: str | None = None) -> AsyncIterator[str]:
    """Журнал и действующее лицо прогона — без базы.

    Отдельно от сессии намеренно: не всякому заданию нужна база. Отправка сообщения в
    Telegram или проверка внешней системы обходятся без неё, и требовать от них
    подключения значило бы ронять их, когда база недоступна, а дело не в ней.
    """
    request_id = normalize_request_id(job_id)

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id, job=name)
    set_actor(Actor(kind=ActorKind.JOB))

    try:
        yield request_id
    finally:
        set_actor(Actor())
        structlog.contextvars.clear_contextvars()


@asynccontextmanager
async def job_scope(name: str, *, job_id: str | None = None) -> AsyncIterator[AsyncSession]:
    """То же плюс сессия: фиксация при успехе, откат при исключении."""
    async with job_context(name, job_id=job_id):
        async for session in session_scope():
            yield session


def job[T](handler: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Превращает функцию в фоновое задание.

    Падение задания **не роняет воркер**: исключение записывается в лог вместе с
    идентификатором прогона и уходит на повтор. После исчерпания попыток пишется отдельная
    строка — её и ищут, когда разбираются, почему чего-то не произошло.

    Своей «мёртвой очереди» таблицей здесь нет намеренно: у неё не было бы читателя.
    Провалившееся задание остаётся в результатах ARQ и в логе строкой `job_exhausted`;
    отдельное хранилище заводится тогда, когда появится тот, кто его разбирает.
    """

    @wraps(handler)
    async def run(ctx: dict[str, Any], *args: Any, **kwargs: Any) -> T:
        name = handler.__name__
        attempt = int(ctx.get("job_try", 1))

        try:
            return await handler(ctx, *args, **kwargs)
        except Exception as failure:
            if attempt >= MAX_TRIES:
                logger.error(
                    "job_exhausted",
                    job=name,
                    attempt=attempt,
                    error=str(failure),
                    exc_info=True,
                )
                raise

            delay = retry_delay(attempt)
            logger.warning(
                "job_failed_will_retry",
                job=name,
                attempt=attempt,
                retry_in_seconds=int(delay.total_seconds()),
                error=str(failure),
            )
            raise Retry(defer=delay) from failure

    return run
