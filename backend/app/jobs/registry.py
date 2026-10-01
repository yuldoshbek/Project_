"""Список задач и правило «работа за период делается один раз».

Идемпотентность здесь не пожелание, а механика. Расписание доставляет вызов «по
возможности»: может пропустить, может позвать дважды, может позвать две функции
одновременно. Поэтому:

- у каждой задачи есть **период** — то, за что отвечает прогон: сутки у сводки, час у
  проверки сроков;
- пара «задача + период» уникальна в базе, и вторая вставка падает, а не «тоже работает»;
- неудачный прогон период не занимает: одна ошибка не должна отменять задачу до конца
  суток;
- брошенный прогон занимает период не дольше `ABANDONED_AFTER`: процесс, убитый
  посреди работы, не должен заклинить задачу навсегда;
- пропущенный период задача догоняет сама — обработчик смотрит на состояние, а не на
  календарь вызовов;
- у задачи может быть **условие «пора»** (`Job.due`): расписание зовёт утреннюю сводку
  каждые десять минут, а время сводки назначает помощник. «Ещё не время» — не прогон, и
  строки в базе после себя не оставляет;
- обработчик может **отпустить период** (`Release`): работать оказалось не для чего или
  внешняя служба не приняла работу. Записанное им при этом остаётся — в отличие от
  падения, которое откатывает всё.

Что задача **не** делает: не длится минутами. Тяжёлый разбор таблицы «Ижро» идёт в
обработчике загрузки по частям — здесь для него нет ни времени функции, ни смысла.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Literal
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.push import PushSender
from app.domain.errors import ConflictError, NotFoundError
from app.repos.models import JobRun

logger = structlog.get_logger(__name__)

STATUS_RUNNING: Final = "running"
STATUS_DONE: Final = "done"
STATUS_FAILED: Final = "failed"
STATUS_NOT_DUE: Final = "not_due"
"""Не пора или не для чего: условие задачи не выполнено либо обработчик отпустил период
(`Release`). Не пишется в базу — это ответ, а не прогон."""

ABANDONED_AFTER = timedelta(minutes=10)
"""Прогон, который «выполняется» дольше этого, брошен, и период снова свободен.

Откуда число: функция на Vercel живёт не дольше 60 секунд (`vercel.json`, `maxDuration`),
а задачи здесь по устройству короткие — сводка и снимок укладываются в секунды. Десять
минут — десятикратный запас над самым долгим законным прогоном; дольше «выполняется»
только тот, кого уже некому завершить.

Откуда такой прогон вообще берётся: сейчас отметка `running` фиксируется одной
транзакцией с результатом, и при падении процесса откатывается вместе с ним. Но достаточно
одного прогона, прерванного между фиксацией отметки и результата — ручная правка, другой
запускающий код на сервере агентства, будущая отметка «начато» отдельной транзакцией, — и
без этого правила период оказался бы занят навсегда: каждое следующее утро сводка
отвечала бы «уже выполняется».
"""


@dataclass(frozen=True, slots=True)
class JobContext:
    """Что известно задаче: сессия, момент вызова, часовой пояс и отправитель уведомлений.

    Время приходит аргументом, а не берётся внутри обработчика: иначе задачу нельзя
    проверить на «вчера» и «завтра», а значит, нельзя проверить вовсе. Отправитель — по той
    же причине: в тестах вместо службы уведомлений стоит подделка.
    """

    session: AsyncSession
    now: datetime
    timezone: ZoneInfo
    push: PushSender


@dataclass(frozen=True, slots=True)
class Release:
    """Обработчик отпускает период: прогон его не занимает, а записанное остаётся.

    Не исключение, потому что это не падение. Падение откатывает работу целиком — половина
    сводки хуже никакой. Здесь же работа сделана честно, и её след нужен: уведомление без
    отметки доставки, подписки, которые служба назвала отключёнными. Откатить их значило бы
    завтра снова стучаться в отключённый адрес.

    - `not_due` — работать оказалось не для чего (сводку некому доставить): как «ещё не
      время», никакой строки о прогоне;
    - `failed` — работа не удалась по внешней причине: строка `failed` с текстом `error`,
      которая период не занимает. Вызывающий видит неудачу — эндпоинт расписания отвечает
      503, командная строка выходит с ненулевым кодом, — и следующий вызов пробует снова.
    """

    status: Literal["not_due", "failed"]
    result: dict[str, Any]
    error: str | None = None


Handler = Callable[[JobContext], Awaitable[dict[str, Any] | Release]]
Gate = Callable[[JobContext], Awaitable[str | None]]
PeriodKey = Callable[[datetime, ZoneInfo], str]

_RUN_STATE = ("status", "started_at", "finished_at", "result", "error")
"""Поля строки прогона, которые повторный прогон перезаписывает, а отпущенный — возвращает."""


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
    due: Gate | None = None
    """Пора ли работать в этот вызов: `None` в ответ — пора, строка — почему ещё нет (она
    уходит в результат `not_due`). Без условия — пора всегда."""


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
    push: PushSender,
    now: datetime | None = None,
    timezone: str = "Asia/Tashkent",
    force: bool = False,
) -> JobResult:
    """Выполняет задачу один раз за её период.

    `force` нужен разработке и разбору происшествий: он позволяет прогнать задачу повторно,
    не дожидаясь следующего периода и назначенного времени. В расписании его нет — иначе
    идемпотентность отключалась бы одним параметром.

    Условие «пора» проверяется после «уже сделано» и до отметки о начале: сделанная работа
    отвечает «сделано» и после назначенного часа, а «ещё не время» не оставляет строки,
    которая заняла бы период.

    Повторный прогон **занимает строку прежнего**, а не заводит вторую: уникальность пары
    «задача + период» держит частичный индекс, и вторая строка со статусом не `failed`
    упала бы на нём. Строка периода описывает последний прогон за этот период; прежний
    результат остаётся в логе (`job_forced`). Если повторный прогон упадёт или отпустит
    период (`Release`), строка вернёт прежнее состояние — удачный результат не теряется
    из-за неудачной попытки.
    """
    jobs = all_jobs()
    job = jobs.get(name)
    if job is None:
        raise NotFoundError(f"Нет задачи «{name}». Есть: {', '.join(sorted(jobs))}")

    moment = now or datetime.now(UTC)
    zone = ZoneInfo(timezone)
    period = job.period(moment, zone)

    existing = await session.scalar(
        select(JobRun).where(
            JobRun.name == name,
            JobRun.period == period,
            JobRun.status != STATUS_FAILED,
        )
    )
    abandoned = (
        existing is not None
        and existing.status == STATUS_RUNNING
        and moment - existing.started_at > ABANDONED_AFTER
    )
    if existing is not None and not (force or abandoned):
        logger.info("job_skipped", job=name, period=period)
        return JobResult(name=name, period=period, status=existing.status, skipped=True)

    context = JobContext(session=session, now=moment, timezone=zone, push=push)
    if job.due is not None and not force:
        reason = await job.due(context)
        if reason is not None:
            logger.info("job_not_due", job=name, period=period, reason=reason)
            return JobResult(
                name=name, period=period, status=STATUS_NOT_DUE, result={"reason": reason}
            )

    previous: dict[str, Any] | None = None
    if existing is not None:
        previous = {field: getattr(existing, field) for field in _RUN_STATE}
        logger.info(
            "job_forced" if force else "job_abandoned_run_taken_over",
            job=name,
            period=period,
            previous_status=existing.status,
            previous_started_at=existing.started_at.isoformat(),
            previous_result=existing.result,
        )
        run = existing
        run.started_at = moment
        run.finished_at = None
        run.status = STATUS_RUNNING
        run.result = None
        run.error = None
    else:
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

    if isinstance(payload, Release):
        return await _release(
            session, run, previous, payload, name=name, period=period, started_at=moment
        )

    run.status = STATUS_DONE
    run.finished_at = datetime.now(UTC)
    run.result = payload
    await session.flush()
    logger.info("job_done", job=name, period=period, **payload)
    return JobResult(name=name, period=period, status=STATUS_DONE, result=payload)


async def _release(
    session: AsyncSession,
    run: JobRun,
    previous: dict[str, Any] | None,
    release: Release,
    *,
    name: str,
    period: str,
    started_at: datetime,
) -> JobResult:
    """Прогон отпускает период, а записанное обработчиком остаётся в той же транзакции.

    Своя строка прогона удаляется, чужая — прежняя строка периода, которую занял повторный
    или брошенный прогон, — получает назад своё состояние: неудачная попытка не стирает
    удачный результат. Неудача пишется отдельной строкой `failed` — такие строки период не
    занимают (`run_job`).
    """
    if previous is None:
        await session.delete(run)
    else:
        for field, value in previous.items():
            setattr(run, field, value)
    if release.status == STATUS_FAILED:
        session.add(
            JobRun(
                name=name,
                period=period,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                status=STATUS_FAILED,
                result=release.result,
                error=release.error[:500] if release.error else None,
            )
        )
        logger.warning("job_failed", job=name, period=period, error=release.error, **release.result)
    else:
        logger.info("job_not_due", job=name, period=period, **release.result)
    await session.flush()
    return JobResult(name=name, period=period, status=release.status, result=release.result)


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
