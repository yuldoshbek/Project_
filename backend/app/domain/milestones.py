"""Вехи проекта: что хранится и что вычисляется.

«Пропущена» — не состояние вехи, а следствие наступившего срока, и хранить его нельзя по
той же причине, по которой нельзя хранить просрочку задачи (инвариант 1): хранимое
значение теряет исходное. Веха бывает запланированной и пропущенной одновременно — она
всё ещё запланирована, просто срок прошёл; один столбец такого не выражает, а фоновое
задание, переписывающее статусы по ночам, отстаёт ровно на сутки.

Поэтому в базе живут признак «пройдена» и дата прохождения (ТЗ 3.1), а «пропущена»
появляется на выдаче.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum


class MilestoneStatus(StrEnum):
    """То, что показывается: решение человека плюс ход времени."""

    PLANNED = "planned"
    PASSED = "passed"
    MISSED = "missed"


def status_of(*, is_passed: bool, due_on: date, today: date) -> MilestoneStatus:
    """Статус вехи с учётом наступившего срока.

    Пройденная веха остаётся пройденной, даже если её закрыли позже срока: она отвечает
    на вопрос «сделали ли», а не «успели ли». На второй вопрос отвечает `passed_late`, и
    это уже отчётность, а не состояние.
    """
    if is_passed:
        return MilestoneStatus.PASSED
    if due_on < today:
        return MilestoneStatus.MISSED
    return MilestoneStatus.PLANNED


def passed_late(*, passed_on: date | None, due_on: date) -> bool:
    """Успели ли к сроку. Нужен отчёту «держим ли мы свои сроки» (ТЗ 5)."""
    return passed_on is not None and passed_on > due_on


def shift_days(*, original_due_on: date | None, due_on: date) -> int:
    """На сколько дней веху переносили относительно первого срока (ТЗ 3.1).

    Исходный срок ведёт система, а не человек: он проставляется при создании и больше не
    меняется. Ноль означает, что переносов не было, — и это единственное, что он может
    означать.
    """
    if original_due_on is None:
        return 0
    return (due_on - original_due_on).days
