"""Проект и программа: что ими является и как считается готовность.

Здесь только правила. Ни FastAPI, ни SQLAlchemy домен не знает (CLAUDE.md, границы
слоёв), и это не формальность: одно и то же правило нужно карточке проекта, Пульту,
отчёту недели и сценарию «что если». Две реализации разойдутся в цифрах, и доверия не
будет ни к одной.

Сигналы считает не этот модуль, а `app.domain.attention`: проект попадает в лестницу
внимания наравне с задачей, вехой и поручением, и правило у них общее.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.domain.dictionaries import ProjectStatus
from app.domain.errors import RuleViolationError

MIN_READINESS = 0
MAX_READINESS = 100

DEFAULT_IMPEDIMENT_STALE_DAYS = 14
"""Через сколько дней строка «что мешает» перестаёт считаться действующей проблемой.

Порог лежит в справочнике и меняется без разработчика (ТЗ 3.9) — здесь только значение
по умолчанию на случай, если строки в справочнике ещё нет.
"""

NESTING_DEPTH = 1
"""Одна ступень вложенности: у программы есть подпроекты, у подпроекта — нет (ТЗ 3.1).

Ограничение не техническое. Дерево произвольной глубины требует показа деревом, а на
телефоне дерево не читается; две ступени отвечают на вопрос «где мы по программе», а
третья уже отвечает на вопрос «как устроена работа», которого руководитель не задаёт.
"""


def impediment_is_stale(*, updated_at: datetime | None, now: datetime, stale_days: int) -> bool:
    """Устарела ли строка «что мешает».

    Запись месячной давности говорит не о препятствии, а о том, что её забыли обновить.
    Считать её за действующую проблему — значит держать на Пульте тревогу, которой,
    возможно, давно нет, и приучить не обращать на тревогу внимания.
    """
    if updated_at is None:
        return False
    return updated_at < now - timedelta(days=stale_days)


def has_active_impediment(
    *, impediment: str | None, updated_at: datetime | None, now: datetime, stale_days: int
) -> bool:
    """Есть ли действующая помеха — то, что попадает в «что мешает и кто может снять»."""
    if not (impediment or "").strip():
        return False
    return not impediment_is_stale(updated_at=updated_at, now=now, stale_days=stale_days)


def readiness(
    *, passed_milestones: int, total_milestones: int, done_tasks: int, total_tasks: int
) -> int:
    """Готовность в процентах — по закрытым вехам и задачам (ТЗ 3.1).

    **Считается, а не вводится.** Ручной процент — это поле, которое помощник обязан
    поддерживать, и первое, что перестаёт соответствовать действительности: стоимость
    ввода определяет, выживет ли продукт (ТЗ 1).

    Вехи и задачи складываются в общий счёт, а не усредняются попарно: проект с десятью
    вехами и одной задачей не должен зависеть от этой задачи наполовину.

    Проект, в котором нет ни вех, ни задач, готов на ноль, а не на сто: пустота не
    является завершённостью.
    """
    total = total_milestones + total_tasks
    if total <= 0:
        return 0
    return round((passed_milestones + done_tasks) * 100 / total)


def schedule_lag(*, started_on: date, due_on: date, today: date, readiness_pct: int) -> int:
    """Отставание от плана в днях (ТЗ 4).

    Доля прошедшего времени минус готовность, переведённая обратно в дни. Отрицательное
    значение — опережение; оно возвращается как есть, потому что «идём с запасом» — такой
    же ответ, как «отстаём на девять дней».

    Проект длиной в день исчерпан целиком — делить на ноль нечего.
    """
    span = (due_on - started_on).days
    if span <= 0:
        return 0
    elapsed = max(0.0, (today - started_on).days / span)
    return round((elapsed - readiness_pct / 100) * span)


def validate_dates(*, started_on: date, due_on: date) -> None:
    """Срок не бывает раньше начала."""
    if due_on < started_on:
        raise RuleViolationError(
            "Плановый срок завершения не может быть раньше даты начала",
            detail=f"начало {started_on.isoformat()}, срок {due_on.isoformat()}",
        )


def validate_status_reason(*, status: ProjectStatus, reason: str | None) -> None:
    """Пауза и отмена требуют причины (ТЗ 3.1).

    Без неё через месяц никто не помнит, чего ждёт приостановленный проект, и возобновить
    его некому: причина — это то, что снимает паузу.
    """
    if status.requires_reason and not (reason or "").strip():
        raise RuleViolationError(
            "Для этого статуса нужно указать причину",
            detail=f"статус «{status.value}» требует заполненного поля причины",
        )


def validate_nesting(*, parent_has_parent: bool) -> None:
    """Вложенность — одна ступень (ТЗ 3.1)."""
    if parent_has_parent:
        raise RuleViolationError(
            "Подпроект нельзя вложить в подпроект",
            detail="вложенность в ORBITA одноступенчатая: программа → подпроект",
        )
