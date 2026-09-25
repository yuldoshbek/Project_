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
from app.domain.dictionaries import SettingKey
from app.domain.pult import MILESTONES, PROJECTS, TASKS, DeadlineMoves
from app.domain.pult import deadline_moves as moves_of
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


async def load_thresholds(session: AsyncSession) -> Thresholds:
    """Пороги из справочника одним запросом. Значения по умолчанию — на пустую таблицу."""
    stored = await load_settings(session)
    return Thresholds(
        burn_days=int(stored.get(SettingKey.BURN_DAYS, DEFAULT_BURN_DAYS)),
        quiet_days=int(stored.get(SettingKey.QUIET_DAYS, DEFAULT_QUIET_DAYS)),
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
) -> DeadlineMoves:
    """«Держим ли мы свои сроки?»: переносы и суммарный сдвиг за период — по журналу."""
    entries = await read_model.audit_entries(
        session,
        since=now - timedelta(days=period_days),
        entity_types=(PROJECTS, MILESTONES, TASKS),
    )
    return moves_of(entries, zone=zone, period_days=period_days, top=top)


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
