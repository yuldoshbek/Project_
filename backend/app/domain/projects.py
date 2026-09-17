"""Проект: что им является и когда он в беде.

Здесь только правила. Ни FastAPI, ни SQLAlchemy домен не знает (CLAUDE.md, границы
слоёв), и это не формальность: светофор считают четыре разных места — карточка проекта,
дашборд, сводка в Telegram и ответ SETA. Две реализации одного правила разойдутся в
цифрах, и доверия не будет ни к одной.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum

from app.domain.dictionaries import Health, ProjectStatus
from app.domain.errors import RuleViolationError


class ProjectKind(StrEnum):
    """Проект или мини-проект (ТЗ 6.1)."""

    PROJECT = "project"
    MINI = "mini"

    @property
    def requires_milestones(self) -> bool:
        """Мини-проект живёт без вех.

        Требовать их — значит заставить помощника придумывать этапы там, где работа
        занимает неделю. Придуманные этапы никто не закрывает, и через месяц все
        мини-проекты выглядят просроченными.
        """
        return self is ProjectKind.PROJECT


SHARE_EXTERNALLY_DEFAULT = True
"""Новый проект по умолчанию можно показывать наружу.

Перечисления здесь нет намеренно: `share_externally` — булево
([ADR-0024](../../../docs/adr/ADR-0024-share-externally.md)). Гриф с уровнями снят
заказчиком, а третьего значения — «партнёрам, но не публично» — никто не называл;
перечисление из двух значений это булево плюс словарь, который придётся переводить
на три локали.

Умолчание вынесено именем, а не вписано `True` в схему запроса и в модель порознь:
два умолчания под одним смыслом однажды разойдутся, и разойдутся молча.
"""


class ProgressMode(StrEnum):
    """Откуда берётся процент выполнения."""

    AUTO = "auto"
    """Доля выполненных задач. Значение по умолчанию: считать вручную — лишний ввод."""

    MANUAL = "manual"
    """Ставит куратор. Нужен там, где задачи не отражают долю работы."""


MIN_PROGRESS = 0
MAX_PROGRESS = 100

DEFAULT_IMPEDIMENT_STALE_DAYS = 14
"""Через сколько дней строка «что мешает» перестаёт считаться действующей проблемой.

Допущение по вопросу **Q23**. Порог лежит в справочнике настроек и меняется без
разработчика (ТЗ 6.8) — здесь только значение по умолчанию на случай, если строки в
справочнике ещё нет.
"""


def impediment_is_stale(*, updated_at: datetime | None, now: datetime, stale_days: int) -> bool:
    """Устарела ли строка «что мешает».

    Запись месячной давности говорит не о препятствии, а о том, что её забыли обновить.
    Считать её за действующую проблему — значит держать на главном экране тревогу,
    которой, возможно, давно нет, и приучить не обращать на тревогу внимания.
    """
    if updated_at is None:
        return False
    return updated_at < now - timedelta(days=stale_days)


def has_active_impediment(
    *, impediment: str | None, updated_at: datetime | None, now: datetime, stale_days: int
) -> bool:
    """Есть ли у проекта действующая помеха — то, что попадает в агрегаты (ADR-0016).

    Пустая строка помехой не считается, устаревшая — тоже. Единственное место, где это
    решается: агрегаты главного экрана (ORB-029, ORB-078) берут ответ отсюда, а не
    повторяют условие у себя.
    """
    if not (impediment or "").strip():
        return False
    return not impediment_is_stale(updated_at=updated_at, now=now, stale_days=stale_days)


def health(
    *,
    status: ProjectStatus,
    started_on: date,
    due_on: date,
    today: date,
    warn_days: int,
    warn_ratio: float,
    has_overdue_tasks: bool = False,
) -> Health:
    """Цвет светофора по правилу [ADR-0005](../../../docs/adr/ADR-0005-traffic-light.md).

    Цвет **не хранится**: иначе понадобится пересчёт по расписанию, и цвет будет
    отставать от реальности ровно тогда, когда на него смотрят.

    `warn_days` и `warn_ratio` приходят из справочника настроек и меняются без
    разработчика (ТЗ 6.8). Для приоритета «Срочно» `warn_days` равен нулю: такой проект
    жёлтый с постановки и красный сразу после срока.

    `has_overdue_tasks` пока всегда `False`: задачи появляются в ORB-014. Правило
    записано целиком здесь, чтобы подключение задач было одной строкой, а не поводом
    переписать светофор заново.
    """
    if status.is_terminal:
        # Серый — не «нет данных», а «из светофора исключён». Без него доля зелёного
        # росла бы по мере завершения работ и перестала бы что-либо значить.
        return Health.GREY

    if due_on < today or has_overdue_tasks:
        return Health.RED

    if (due_on - today).days <= warn_days:
        return Health.YELLOW

    if _elapsed_ratio(started_on=started_on, due_on=due_on, today=today) > warn_ratio:
        return Health.YELLOW

    return Health.GREEN


def _elapsed_ratio(*, started_on: date, due_on: date, today: date) -> float:
    """Какая доля отведённого времени прошла.

    Проект, начатый в будущем, не «прошёл на минус сорок процентов»: доля не бывает
    отрицательной. Однодневный срок исчерпан целиком — делить на ноль нечего.
    """
    span = (due_on - started_on).days
    if span <= 0:
        return 1.0
    return max(0.0, (today - started_on).days / span)


def validate_dates(*, started_on: date, due_on: date) -> None:
    """Срок не бывает раньше начала."""
    if due_on < started_on:
        raise RuleViolationError(
            "Плановый срок завершения не может быть раньше даты начала",
            detail=f"начало {started_on.isoformat()}, срок {due_on.isoformat()}",
        )


def validate_status_reason(*, status: ProjectStatus, reason: str | None) -> None:
    """Пауза и отмена требуют причины (ТЗ 7).

    Без неё через месяц никто не помнит, чего ждёт приостановленный проект, и
    возобновить его некому: причина — это то, что снимает паузу.
    """
    if status.requires_reason and not (reason or "").strip():
        raise RuleViolationError(
            "Для этого статуса нужно указать причину",
            detail=f"статус «{status.value}» требует заполненного поля причины",
        )


def validate_progress(value: int) -> None:
    if not MIN_PROGRESS <= value <= MAX_PROGRESS:
        raise RuleViolationError(
            "Процент выполнения задаётся числом от 0 до 100",
            detail=f"получено {value}",
        )


def auto_progress(*, total_tasks: int, done_tasks: int) -> int:
    """Доля выполненных задач в процентах.

    Проект без задач — ноль, а не сто: пустота не является завершённостью. Расчёт
    подключается к изменению статуса задачи в ORB-014, где задачи и появляются.
    """
    if total_tasks <= 0:
        return 0
    return round(done_tasks * 100 / total_tasks)
