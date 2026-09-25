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
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import DueChanges, Item, Ladder, build_ladder, with_due_changes
from app.domain.dictionaries import SettingKey
from app.repos import attention as snapshot
from app.services.dictionaries import load_settings

DEFAULT_BURN_DAYS = 7
DEFAULT_QUIET_DAYS = 14


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
