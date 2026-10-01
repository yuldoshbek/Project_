"""Задача: когда она просрочена и куда из какого состояния можно перейти.

Просрочка здесь **вычисляется, а не хранится**
([ADR-0004](../../../docs/adr/ADR-0004-overdue-is-computed.md)). Хранить её в статусе —
значит потерять исходное состояние: «просрочена» отвечает на вопрос «наступил ли срок»,
а `status` — на вопрос «что с работой». Задача бывает и «в работе», и просроченной
одновременно, а один столбец такого не выражает.
"""

from __future__ import annotations

from datetime import date, datetime, time, tzinfo
from enum import StrEnum

from app.domain.dictionaries import TaskStatus
from app.domain.errors import ConflictError, RuleViolationError

# Куда можно перейти из каждого состояния.
#
# Граф разрешает исправлять ошибки и запрещает перепрыгивать смысл. Из «Выполнена»
# нельзя вернуться сразу в «Новая»: работа, которую делали, не становится неначатой —
# сначала «В работе». Из «Новая» нельзя попасть сразу в «Выполнена»: иначе учёт
# показывает выполненными задачи, которых никто не делал, и по нему нельзя понять
# загрузку.
ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.NEW: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.IN_PROGRESS: frozenset(
        {TaskStatus.NEW, TaskStatus.IN_REVIEW, TaskStatus.DONE, TaskStatus.CANCELLED}
    ),
    TaskStatus.IN_REVIEW: frozenset(
        {TaskStatus.IN_PROGRESS, TaskStatus.DONE, TaskStatus.CANCELLED}
    ),
    # Переоткрытие есть, отмена выполненного — нет: отменяют то, что не сделали.
    TaskStatus.DONE: frozenset({TaskStatus.IN_PROGRESS}),
    TaskStatus.CANCELLED: frozenset({TaskStatus.NEW, TaskStatus.IN_PROGRESS}),
}


def validate_transition(*, current: TaskStatus, target: TaskStatus) -> None:
    """Проверяет переход между состояниями работы.

    Повтор того же статуса разрешён: одно и то же изменение, посланное дважды, не
    должно отличаться от посланного один раз.
    """
    if current is target:
        return
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ConflictError(
            "Такой переход статуса не разрешён",
            detail=(
                f"из «{current.value}» можно перейти в: "
                f"{', '.join(sorted(status.value for status in ALLOWED_TRANSITIONS[current]))}"
            ),
        )


def is_overdue(*, due_at: datetime | None, status: TaskStatus, now: datetime) -> bool:
    """Наступил ли срок у незакрытой задачи (ADR-0004).

    Задача без срока не бывает просроченной: срок, которого не назначали, не наступает.
    """
    if due_at is None or status.is_terminal:
        return False
    return due_at < now


def days_overdue(*, due_at: datetime | None, status: TaskStatus, now: datetime) -> int:
    """На сколько полных суток задача опоздала.

    Ноль — не «сегодня срок», а «не просрочена»: просрочка начинается с первой полной
    минуты после срока, а первые сутки ещё не набежали. Различие видно в интерфейсе:
    просрочка показывается признаком, а число — пояснением к нему.
    """
    if not is_overdue(due_at=due_at, status=status, now=now):
        return 0
    assert due_at is not None
    return (now - due_at).days


TITLE_MAX_LENGTH = 300
"""Как у столбца `tasks.title`."""

DUE_TIME = time(18, 0)
"""Во сколько наступает срок, названный днём: конец рабочего дня по Ташкенту.

Человек назначает срок днём («к пятнице»), а хранится момент (`tasks.due_at`, инвариант 8).
Полночь начала дня сделала бы задачу просроченной с утра того дня, к которому её просили,
а полночь конца — «сегодняшней» ещё и ночью. Конец рабочего дня — то, что имеют в виду.
"""

WEEK_DAYS = 7
"""«Ближайшая неделя» в списке — семь дней вперёд, как порог «горит» по умолчанию (ТЗ 4)."""


class Horizon(StrEnum):
    """«К какому сроку» — группа списка задач. Порядок объявления — порядок показа."""

    OVERDUE = "overdue"
    TODAY = "today"
    TOMORROW = "tomorrow"
    WEEK = "week"
    LATER = "later"
    NONE = "none"
    CLOSED = "closed"


def horizon_of(*, status: TaskStatus, due_on: date | None, today: date) -> Horizon:
    """Группа задачи по сроку относительно сегодняшнего дня Ташкента.

    Закрытая задача — в своей группе, какой бы срок у неё ни был: список дел отвечает на
    «что делать», а сделанное — на другой вопрос.
    """
    if status.is_terminal:
        return Horizon.CLOSED
    if due_on is None:
        return Horizon.NONE
    days = (due_on - today).days
    if days < 0:
        return Horizon.OVERDUE
    if days == 0:
        return Horizon.TODAY
    if days == 1:
        return Horizon.TOMORROW
    if days <= WEEK_DAYS:
        return Horizon.WEEK
    return Horizon.LATER


def due_moment(day: date, zone: tzinfo) -> datetime:
    """Момент срока для дня: конец рабочего дня (`DUE_TIME`) в поясе агентства."""
    return datetime.combine(day, DUE_TIME, zone)


def validate_title(title: str) -> str:
    """Название задачи — единственное обязательное поле (ТЗ 7)."""
    if "\x00" in title:
        raise RuleViolationError("В названии задачи есть недопустимый символ")
    value = title.strip()
    if not value:
        raise RuleViolationError("Напишите, что нужно сделать")
    if len(value) > TITLE_MAX_LENGTH:
        raise RuleViolationError(f"Название длиннее {TITLE_MAX_LENGTH} символов")
    return value
