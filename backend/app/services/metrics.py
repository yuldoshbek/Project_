"""Сервис показателей: единственное место, откуда берутся сигналы.

Это инвариант 2 в виде кода. Экран, отчёт, уведомление и сценарий «что если» берут числа
только отсюда — два источника расчёта разошлись бы, и доверия не было бы ни к одному.
Проверяется тестом: числа утренней сводки совпадают с лестницей на тех же данных.

**Как устроен.** Три шага, каждый в своём слое:

1. пороги — из справочника (ТЗ 3.9), одним запросом;
2. снимок незавершённых записей — `app.repos.attention`, только чтение;
3. расчёт — `app.domain.attention.build_ladder`, чистая функция.

**«Что если» — тот же путь с подменённым снимком.** `what_if` получает новые сроки,
применяет их к снимку в памяти и считает лестницу тем же кодом. Записывать в базу ему
нечем по устройству: изменения не касаются ни одной модели, только копий строк снимка.
Применить «что если» — отдельное действие сервиса правки, которое появится вместе с
экраном (критерий 3 блока 1).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import (
    DueChanges,
    Holder,
    Item,
    Ladder,
    build_ladder,
    with_due_changes,
)
from app.domain.attention import holders as holders_of
from app.domain.dictionaries import ProjectStatus, SettingKey
from app.domain.projects import (
    DEFAULT_IMPEDIMENT_STALE_DAYS,
    impediment_is_stale,
    project_lag,
    project_readiness,
)
from app.domain.pult import (
    DECISIONS,
    MILESTONES,
    PROJECTS,
    TASKS,
    AuditEntry,
    DeadlineMoves,
    PeriodTotals,
    due_shift,
)
from app.domain.pult import deadline_moves as moves_of
from app.domain.pult import period_totals as totals_of
from app.repos import attention as snapshot
from app.repos import pult as read_model
from app.services.dictionaries import load_settings

DEFAULT_BURN_DAYS = 7
DEFAULT_QUIET_DAYS = 14

MOVES_PERIOD_DAYS = 30
"""«Держим ли мы свои сроки?» — за месяц: короче не видно привычки переносить, длиннее
в ответ попадают переносы, о которых уже договорились и забыли."""

MOVES_TOP = 5
"""Сколько самых переносимых записей показать: на телефоне больше пяти не читают."""


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Пороги лестницы, прочитанные один раз на весь расчёт."""

    burn_days: int
    quiet_days: int
    impediment_stale_days: int = DEFAULT_IMPEDIMENT_STALE_DAYS


async def load_thresholds(session: AsyncSession) -> Thresholds:
    """Пороги из справочника одним запросом. Значения по умолчанию — на пустую таблицу."""
    stored = await load_settings(session)
    return Thresholds(
        burn_days=int(stored.get(SettingKey.BURN_DAYS, DEFAULT_BURN_DAYS)),
        quiet_days=int(stored.get(SettingKey.QUIET_DAYS, DEFAULT_QUIET_DAYS)),
        impediment_stale_days=int(
            stored.get(SettingKey.IMPEDIMENT_STALE_DAYS, DEFAULT_IMPEDIMENT_STALE_DAYS)
        ),
    )


@dataclass(frozen=True, slots=True)
class Progress:
    """Где проект по плану: готовность и отставание — одна пара на все экраны."""

    readiness: int
    lag_days: int


def progress(
    *,
    status: ProjectStatus,
    started_on: date,
    due_on: date,
    today: date,
    passed_milestones: int,
    total_milestones: int,
    done_tasks: int,
    total_tasks: int,
) -> Progress:
    """Готовность и отставание проекта (ТЗ 3.1, 4).

    Отсюда их берут карточка, таблица, таймлайн и «что если»: отставание при другом сроке
    считается этой же функцией, а не второй формулой рядом с экраном.
    """
    ready = project_readiness(
        status=status,
        passed_milestones=passed_milestones,
        total_milestones=total_milestones,
        done_tasks=done_tasks,
        total_tasks=total_tasks,
    )
    return Progress(
        readiness=ready,
        lag_days=project_lag(
            status=status, started_on=started_on, due_on=due_on, today=today, readiness_pct=ready
        ),
    )


def impediment_stale(*, updated_on: date | None, today: date, thresholds: Thresholds) -> bool:
    """Устарела ли строка «что мешает» — порог из справочника (ТЗ 3.9), по дням Ташкента."""
    return impediment_is_stale(
        updated_on=updated_on, today=today, stale_days=thresholds.impediment_stale_days
    )


async def ladder(
    session: AsyncSession,
    *,
    today: date,
    zone: ZoneInfo,
    thresholds: Thresholds | None = None,
) -> Ladder:
    """Лестница внимания по всем разделам — то, что показывает Пульт."""
    limits = thresholds or await load_thresholds(session)
    items = await snapshot.load_items(session, zone=zone)
    return build_ladder(
        items, today=today, burn_days=limits.burn_days, quiet_days=limits.quiet_days
    )


def holders(ladder: Ladder) -> list[Holder]:
    """«Кто держит» — по строкам той же лестницы, а не отдельным подсчётом."""
    return holders_of(ladder.rows)


async def deadline_moves(
    session: AsyncSession,
    *,
    now: datetime,
    zone: ZoneInfo,
    period_days: int = MOVES_PERIOD_DAYS,
    top: int = MOVES_TOP,
    since: datetime | None = None,
) -> DeadlineMoves:
    """«Держим ли мы свои сроки?»: переносы и суммарный сдвиг за период — по журналу.

    По умолчанию — последние `period_days` до `now`; отчёт передаёт свои границы.
    """
    entries = await read_model.audit_entries(
        session,
        since=since or now - timedelta(days=period_days),
        until=now,
        entity_types=(PROJECTS, MILESTONES, TASKS),
    )
    return moves_of(entries, zone=zone, period_days=period_days, top=top)


def moves_count(entries: Iterable[AuditEntry], *, zone: ZoneInfo) -> int:
    """Сколько раз срок записи переносили позже — за всю её жизнь, по журналу.

    Правило то же, что у «Держим ли мы свои сроки?» (`app.domain.pult.deadline_moves`):
    перенос — сдвиг позже, подтянутый срок переносом не считается. Иначе карточка и Пульт
    назвали бы разное число переносов одной и той же работы.
    """
    count = 0
    for entry in entries:
        shift = due_shift(entry, zone)
        if shift is not None and shift[1] > shift[0]:
            count += 1
    return count


async def period_totals(
    session: AsyncSession, *, start: datetime, end: datetime, zone: ZoneInfo
) -> PeriodTotals:
    """Итоги периода для отчёта недели и месяца — по журналу, тем же правилом."""
    entries = await read_model.audit_entries(
        session,
        since=start,
        until=end,
        entity_types=(PROJECTS, MILESTONES, TASKS, DECISIONS),
    )
    return totals_of(entries, zone=zone)


async def what_if(
    session: AsyncSession,
    *,
    today: date,
    zone: ZoneInfo,
    changes: DueChanges,
    thresholds: Thresholds | None = None,
) -> tuple[Ladder, Ladder]:
    """Лестница сейчас и лестница при других сроках — для сравнения на экране.

    Обе считает один код по одному снимку, поэтому разница между ними — ровно следствие
    изменённых сроков, а не второго расчёта.
    """
    limits = thresholds or await load_thresholds(session)
    items = await snapshot.load_items(session, zone=zone)

    def count(rows: Iterable[Item]) -> Ladder:
        return build_ladder(
            rows,
            today=today,
            burn_days=limits.burn_days,
            quiet_days=limits.quiet_days,
        )

    return count(items), count(with_due_changes(items, changes))
