"""Список задач и правило «работа за период делается один раз».

Идемпотентность здесь не пожелание, а механика. Расписание доставляет вызов «по
возможности»: может пропустить, может позвать дважды, может позвать две функции
одновременно. Поэтому:

- у каждой задачи есть **период** — то, за что отвечает прогон: сутки у сводки, час у
  проверки сроков;
- пара «задача + период» уникальна в базе, и вторая вставка падает, а не «тоже работает»;
- неудачный прогон период не занимает: одна ошибка не должна отменять задачу до конца
  суток;
- пропущенный период задача догоняет сама — обработчик смотрит на состояние, а не на
  календарь вызовов.

Что задача **не** делает: не длится минутами. Тяжёлый разбор таблицы «Ижро» идёт в
обработчике загрузки по частям — здесь для него нет ни времени функции, ни смысла.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import ConflictError, NotFoundError
from app.repos.models import JobRun

logger = structlog.get_logger(__name__)

STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class JobContext:
    """Что известно задаче: сессия, момент вызова и часовой пояс пользователей.

    Время приходит аргументом, а не берётся внутри обработчика: иначе задачу нельзя
    проверить на «вчера» и «завтра», а значит, нельзя проверить вовсе.
    """

    session: AsyncSession
    now: datetime
    timezone: ZoneInfo


Handler = Callable[[JobContext], Awaitable[dict[str, Any]]]
PeriodKey = Callable[[datetime, ZoneInfo], str]


def daily_period(now: datetime, timezone: ZoneInfo) -> str:
    """Сутки по Ташкенту.

    По местному времени, а не по UTC: «утренняя сводка за 20 сентября» — это сутки того,
    кто её читает. По UTC граница суток проходила бы в пять утра по Ташкенту, и сводка
    после полуночи считалась бы вчерашней.
    """
    return now.astimezone(timezone).strftime("%Y-%m-%d")


def hourly_period(now: datetime, timezone: ZoneInfo) -> str:
    return now.astimezone(timezone).strftime("%Y-%m-%dT%H")


@dataclass(frozen=True, slots=True)
class Job:
    """Описание задачи."""

    name: str
    title: str
    period: PeriodKey
    handler: Handler


@dataclass(slots=True)
class JobResult:
    """Чем закончился прогон. Это же уходит в сводку прогона расписания."""

    name: str
    period: str
    status: str
    result: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False
    """Работа за этот период уже сделана. Не ошибка: так выглядит второй вызов."""


_REGISTRY: dict[str, Job] = {}


def register(job: Job) -> Job:
    if job.name in _REGISTRY:
        raise RuntimeError(f"задача {job.name} уже зарегистрирована")
    _REGISTRY[job.name] = job
    return job


def all_jobs() -> dict[str, Job]:
    """Зарегистрированные задачи.

    Функция, а не словарь: обработчики регистрируются при импорте `app.jobs.handlers`, и
    обращение через функцию не зависит от того, что и в каком порядке успели импортировать.
    """
    from app.jobs import handlers  # noqa: F401  (регистрация при импорте — в этом и смысл)

    return dict(_REGISTRY)


async def run_job(
    session: AsyncSession,
    name: str,
    *,
    now: datetime | None = None,
    timezone: str = "Asia/Tashkent",
    force: bool = False,
) -> JobResult:
    """Выполняет задачу один раз за её период.

    `force` нужен разработке и разбору происшествий: он позволяет прогнать задачу повторно,
    не дожидаясь следующего периода. В расписании его нет — иначе идемпотентность
    отключалась бы одним параметром.
    """
    jobs = all_jobs()
    job = jobs.get(name)
    if job is None:
        raise NotFoundError(f"Нет задачи «{name}». Есть: {', '.join(sorted(jobs))}")

    moment = now or datetime.now(UTC)
    zone = ZoneInfo(timezone)
    period = job.period(moment, zone)

    done = await session.scalar(
        select(JobRun).where(
            JobRun.name == name,
            JobRun.period == period,
            JobRun.status != STATUS_FAILED,
        )
    )
    if done is not None and not force:
        logger.info("job_skipped", job=name, period=period)
        return JobResult(name=name, period=period, status=done.status, skipped=True)

    run = JobRun(name=name, period=period, started_at=moment, status=STATUS_RUNNING)
    session.add(run)
    try:
        # Отметка о начале уходит в базу до работы: так второй одновременный вызов
        # упирается в уникальность пары «задача + период», а не делает работу параллельно.
        await session.flush()
    except IntegrityError as error:
        await session.rollback()
        logger.info("job_already_running", job=name, period=period)
        raise ConflictError(f"Задача «{name}» за {period} уже выполняется") from error

    context = JobContext(session=session, now=moment, timezone=zone)
    try:
        payload = await job.handler(context)
    except Exception as error:
        # Работа откатывается целиком: половина сделанной сводки хуже отсутствующей.
        # А вот след о падении должен остаться, иначе про неудачу узнают в день, когда
        # понадобится её объяснить, — поэтому он пишется своей транзакцией.
        await session.rollback()
        await _record_failure(name=name, period=period, started_at=moment, error=error)
        logger.exception("job_failed", job=name, period=period)
        raise

    run.status = STATUS_DONE
    run.finished_at = datetime.now(UTC)
    run.result = payload
    await session.flush()
    logger.info("job_done", job=name, period=period, **payload)
    return JobResult(name=name, period=period, status=STATUS_DONE, result=payload)


async def _record_failure(
    *, name: str, period: str, started_at: datetime, error: Exception
) -> None:
    """Пишет отметку о падении отдельной транзакцией.

    Неудачный прогон период не занимает: запрос на «уже сделано» пропускает записи со
    статусом `failed`, и следующий вызов расписания попробует снова.
    """
    from app.repos.database import session_scope

    async for own in session_scope():
        own.add(
            JobRun(
                name=name,
                period=period,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                status=STATUS_FAILED,
                error=str(error)[:500],
            )
        )
