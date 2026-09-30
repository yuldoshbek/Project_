"""Программы — правила раздела (ТЗ 2, 4, 5).

Программа — многолетний проект с подпроектами (ТЗ 3.1). Раздел отвечает, где мы по
программам и что должно случиться до конца года; здесь — чистые правила, из которых
сервис показателей собирает ответ: горизонт лет, отсчёт до даты и «успеваем ли к дате».

Два правила ТЗ не называет, и они записаны допущениями (docs/OPEN-QUESTIONS.md): как
считать «успеваем?» — V13, какой горизонт — V14.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

HORIZON_YEARS = 5
"""Горизонт — пять лет от текущего (PLAN, блок 1: «горизонт 2026–2030»; допущение V14)."""

PACE_WINDOW_DAYS = 90
"""Темп «успеваем?» — за последние 90 дней (V13): короче — темп прыгает от одной недели
отпуска, длиннее — в него попадает работа, которую вела уже другая команда."""


class PaceVerdict(StrEnum):
    ON_TRACK = "on_track"
    BEHIND = "behind"
    LITTLE_DATA = "little_data"


@dataclass(frozen=True, slots=True)
class Pace:
    """Ответ на «успеваем ли к дате программы?» со всем, из чего он выведен.

    Фраза на экране называет правило (ТЗ 5): что закрыто за окно, что осталось, куда
    выводит темп. Поэтому здесь не только вердикт, но и числа под ним.
    """

    verdict: PaceVerdict
    window_days: int
    closed: int
    """Закрыто вех и задач за окно."""

    closed_tasks: int
    """Из них задач — по ним решается «мало данных» (ТЗ 4)."""

    min_closed_tasks: int
    remaining: int
    """Осталось вех и задач — того же набора, по которому считается готовность."""

    forecast_on: date | None
    """Когда закроется оставшееся при этом темпе; `None` — мало данных."""

    gap_days: int | None
    """Прогноз минус дата программы: плюс — не успеваем на столько, минус — запас."""


def pace(
    *,
    today: date,
    due_on: date,
    closed: int,
    closed_tasks: int,
    remaining: int,
    min_closed_tasks: int,
    window_days: int = PACE_WINDOW_DAYS,
) -> Pace:
    """«Успеваем?» по темпу закрытия (ТЗ 4; допущение V13).

    Прогноз — сегодня плюс оставшееся, делённое на темп за окно; позже даты программы —
    «не успеваем». Меньше `min_closed_tasks` закрытых задач за окно — «мало данных»: темп
    из трёх закрытых задач — шум, а не прогноз.

    Оставшееся — только то, что заведено: незаведённая работа в прогноз не входит. Это
    видно в самой фразе («осталось 27»), и руководитель судит о ней сам.
    """
    if closed_tasks < min_closed_tasks or closed <= 0:
        return Pace(
            verdict=PaceVerdict.LITTLE_DATA,
            window_days=window_days,
            closed=closed,
            closed_tasks=closed_tasks,
            min_closed_tasks=min_closed_tasks,
            remaining=remaining,
            forecast_on=None,
            gap_days=None,
        )
    if remaining <= 0:
        # Всё заведённое закрыто: не успевать нечему, даже если дата уже прошла. «Не хватает
        # семи дней» при «осталось 0» и кнопка «урезать объём» там, где урезать нечего,
        # были бы неправдой; закрыть программу — решение помощника, а не вывод темпа.
        return Pace(
            verdict=PaceVerdict.ON_TRACK,
            window_days=window_days,
            closed=closed,
            closed_tasks=closed_tasks,
            min_closed_tasks=min_closed_tasks,
            remaining=0,
            forecast_on=today,
            gap_days=0,
        )
    # Целые дни с округлением вверх: остаток в полдня работы — ещё день.
    need = -(-remaining * window_days // closed)
    forecast = today + timedelta(days=need)
    gap = (forecast - due_on).days
    return Pace(
        verdict=PaceVerdict.BEHIND if gap > 0 else PaceVerdict.ON_TRACK,
        window_days=window_days,
        closed=closed,
        closed_tasks=closed_tasks,
        min_closed_tasks=min_closed_tasks,
        remaining=remaining,
        forecast_on=forecast,
        gap_days=gap,
    )


def window_start(today: date, window_days: int = PACE_WINDOW_DAYS) -> date:
    """Последний день до окна: закрытое строго позже него — в темпе."""
    return today - timedelta(days=window_days)


def in_window(day: date | None, *, today: date, window_days: int = PACE_WINDOW_DAYS) -> bool:
    return day is not None and window_start(today, window_days) < day <= today


def horizon(today: date) -> tuple[int, int]:
    """Первый и последний год горизонта."""
    return today.year, today.year + HORIZON_YEARS - 1


def year_end(today: date) -> date:
    """Граница «что должно случиться до конца года» — 31 декабря текущего года."""
    return date(today.year, 12, 31)


def days_left(*, due_on: date, today: date) -> int:
    """Отсчёт: календарных дней до даты; минус — дата прошла (инвариант 8)."""
    return (due_on - today).days
