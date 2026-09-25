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

HORIZON_MONTHS = 12
"""Насколько вперёд разворачивается цикл. Ровно год: дальше даты не решают ничего."""


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

    Дата, которой не существует (31 февраля), пропускается молча: это опечатка при
    заведении цикла, и гадать за человека здесь нельзя — он увидит, что дат нет, и
    поправит месяц.
    """
    months = _months_of(rule, month)

    until = _plus_months(since, HORIZON_MONTHS)
    found: list[date] = []

    for year in range(since.year, until.year + 1):
        if rule is CycleRule.EVERY_N_YEARS and (year - anchor_year) % max(every_years, 1) != 0:
            continue
        for each in months:
            try:
                moment = date(year, each, day)
            except ValueError:
                continue
            if since <= moment <= until:
                found.append(moment)

    return sorted(found)


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
