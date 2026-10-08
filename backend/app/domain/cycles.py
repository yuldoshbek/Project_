"""Годовые циклы: повторяющиеся сроки, которые система разворачивает в даты (ТЗ 3.1).

«Ежегодно в феврале», «ежеквартально», «раз в три года» — это то, что помощник иначе
заводил бы руками по четыре раза в год и однажды забыл бы завести. Система хранит
правило, а даты считает сама: стоимость ввода определяет, выживет ли продукт (ТЗ 1).

Разворачивается **на год вперёд и не дальше**. Календарь на пять лет вперёд — это не
планирование, а список, который никто не читает, и его всё равно придётся пересчитывать
после первого переноса.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from app.domain.errors import RuleViolationError

HORIZON_MONTHS = 12
"""Насколько вперёд разворачивается цикл. Ровно год: дальше даты не решают ничего."""

TITLE_MAX_LENGTH = 300

EVERY_YEARS_MIN = 2
"""«Раз в N лет» — от двух: раз в год — это «ежегодно», и два правила на одно дело
показывали бы его по-разному."""

EVERY_YEARS_MAX = 10
"""Как в базе (`every_years_is_sane`): раз в двадцать лет — уже не цикл, а веха."""

ANCHOR_SPAN_YEARS = 10
"""Год начала «раз в N лет» — в десяти годах от текущего в обе стороны: дальше — опечатка."""


class CycleRule(StrEnum):
    """Как повторяется срок."""

    ANNUAL = "annual"
    """Ежегодно в названном месяце: отчёт по программе космического мониторинга."""

    QUARTERLY = "quarterly"
    """Ежеквартально: сведения в Кабмин."""

    EVERY_N_YEARS = "every_n_years"
    """Раз в N лет: пересмотр дорожной карты."""


def occurrences(
    *,
    rule: CycleRule,
    month: int,
    day: int,
    every_years: int,
    anchor_year: int,
    since: date,
) -> list[date]:
    """Даты цикла на год вперёд от `since`.

    `anchor_year` — год, от которого считается «раз в N лет»: без него цикл «раз в три
    года» не знает, какие именно три года имеются в виду, и ответ зависел бы от того,
    когда его спросили.

    Дата, которой не существует (31 февраля), пропускается молча, а не угадывается: у
    ежеквартального цикла на 31-е апреля нет, остальные кварталы на месте. Цикл, у которого
    такого дня нет ни в одном году, не заводится вовсе (`validate_rule`).
    """
    return dates_between(
        rule=rule,
        month=month,
        day=day,
        every_years=every_years,
        anchor_year=anchor_year,
        since=since,
        until=_plus_months(since, HORIZON_MONTHS),
    )


def next_date(
    *,
    rule: CycleRule,
    month: int,
    day: int,
    every_years: int,
    anchor_year: int,
    since: date,
) -> date | None:
    """Ближайшая дата цикла от `since` — и за горизонтом года.

    Цикл «раз в три года» два года из трёх не даёт ни одной даты на год вперёд, и без
    ближайшей даты его не отличить от опечатки: «дат нет» звучало бы как «проверьте число»,
    хотя проверять нечего. `None` — только если дня нет ни в одном подходящем году
    (30 февраля): 29 февраля в цикле раз в три года наступает раз в двенадцать лет, поэтому
    просмотр — на четыре шага цикла вперёд. Шаги считаются от первого года, который цикл
    признаёт: у цикла «с 2036 года» от текущего их не хватило бы, и настоящий день выглядел
    бы несуществующим.
    """
    start = max(since.year, anchor_year) if rule is CycleRule.EVERY_N_YEARS else since.year
    found = dates_between(
        rule=rule,
        month=month,
        day=day,
        every_years=every_years,
        anchor_year=anchor_year,
        since=since,
        until=date(start + 4 * max(every_years, 1) + 1, 12, 31),
    )
    return found[0] if found else None


def dates_between(
    *,
    rule: CycleRule,
    month: int,
    day: int,
    every_years: int,
    anchor_year: int,
    since: date,
    until: date,
) -> list[date]:
    """Даты цикла с `since` по `until` включительно — и прошедшие: календарь показывает
    дату цикла в просматриваемом месяце, даже если она позади (V16)."""
    months = _months_of(rule, month)
    found: list[date] = []

    for year in range(since.year, until.year + 1):
        if rule is CycleRule.EVERY_N_YEARS and not _counts(year, anchor_year, every_years):
            continue
        for each in months:
            try:
                moment = date(year, each, day)
            except ValueError:
                continue
            if since <= moment <= until:
                found.append(moment)

    return sorted(found)


def _counts(year: int, anchor_year: int, every_years: int) -> bool:
    """Год цикла «раз в N лет» — год начала и каждый N-й после него.

    Годы до начала не в счёт: остаток от деления сам по себе пропустил бы 2027-й при начале
    в 2030-м и шаге 3, а подпись цикла говорит «с 2030 года».
    """
    return year >= anchor_year and (year - anchor_year) % max(every_years, 1) == 0


def horizon(today: date) -> date:
    """Докуда развёрнуты циклы и листается календарь: год от сегодняшнего."""
    return _plus_months(today, HORIZON_MONTHS)


def validate_rule(
    *, rule: CycleRule, month: int, day: int, every_years: int, anchor_year: int, today: date
) -> None:
    """Правило, которое можно завести: числа в пределах и день хоть в каком-то году есть.

    Даты на год вперёд помощник видит до записи, но проверяет сервер: запрос мог прийти
    мимо формы, а цикл на 30 февраля молча не наступил бы никогда.
    """
    if not 1 <= month <= 12:
        raise RuleViolationError("Месяц — от 1 до 12")
    if not 1 <= day <= 31:
        raise RuleViolationError("Число — от 1 до 31")
    if rule is CycleRule.EVERY_N_YEARS:
        if not EVERY_YEARS_MIN <= every_years <= EVERY_YEARS_MAX:
            raise RuleViolationError(f"Раз в {EVERY_YEARS_MIN}–{EVERY_YEARS_MAX} лет")
        if abs(anchor_year - today.year) > ANCHOR_SPAN_YEARS:
            raise RuleViolationError(
                f"Год начала — с {today.year - ANCHOR_SPAN_YEARS} "
                f"по {today.year + ANCHOR_SPAN_YEARS}"
            )
    if (
        next_date(
            rule=rule,
            month=month,
            day=day,
            every_years=every_years,
            anchor_year=anchor_year,
            since=today,
        )
        is None
    ):
        raise RuleViolationError("Такого дня нет ни в одном году: проверьте месяц и число")


def _months_of(rule: CycleRule, month: int) -> tuple[int, ...]:
    """Месяцы, в которые наступает срок.

    У ежеквартального цикла названный месяц не спрашивается: кварталы государственной
    отчётности привязаны к календарю, а не к тому, когда цикл завели.
    """
    if rule is CycleRule.QUARTERLY:
        return (1, 4, 7, 10)
    return (month,)


def _plus_months(moment: date, months: int) -> date:
    """Та же дата через N месяцев.

    Без `dateutil`: одна зависимость ради одного сложения — это зависимость, которую
    потом обновляют, проверяют и объясняют.
    """
    total = moment.month - 1 + months
    year = moment.year + total // 12
    month = total % 12 + 1
    day = min(moment.day, _days_in(year, month))
    return date(year, month, day)


def _days_in(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year + month // 12, month % 12 + 1, 1) - date(year, month, 1)).days
