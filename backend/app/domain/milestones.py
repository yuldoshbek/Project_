"""Вехи проекта: что хранится и что вычисляется.

«Пропущена» — не состояние вехи, а следствие наступившего срока, и хранить его нельзя по
той же причине, по которой нельзя хранить просрочку задачи
([ADR-0004](../../../docs/adr/ADR-0004-overdue-is-computed.md)): хранимое значение теряет
исходное. Веха бывает запланированной и пропущенной одновременно — она всё ещё
запланирована, просто срок прошёл; один столбец такого не выражает, а фоновое задание,
переписывающее статусы по ночам, отстаёт ровно на сутки.

Поэтому в базе живут два значения, `planned` и `done`, а третье появляется на выдаче.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum


class MilestoneState(StrEnum):
    """То, что хранится: решение человека о вехе."""

    PLANNED = "planned"
    DONE = "done"


class MilestoneStatus(StrEnum):
    """То, что показывается: решение человека плюс ход времени."""

    PLANNED = "planned"
    DONE = "done"
    MISSED = "missed"


def effective_status(*, state: MilestoneState, due_on: date, today: date) -> MilestoneStatus:
    """Статус вехи с учётом наступившего срока.

    Выполненная веха остаётся выполненной, даже если её закрыли позже срока: она
    отвечает на вопрос «сделали ли», а не «успели ли». На вопрос «успели ли» отвечает
    сравнение `completed_on` со сроком — и это уже отчётность, а не состояние.
    """
    if state is MilestoneState.DONE:
        return MilestoneStatus.DONE
    if due_on < today:
        return MilestoneStatus.MISSED
    return MilestoneStatus.PLANNED
