"""Управление — правила обхода, порогов и справочников (ТЗ 3.9, 4, 7, критерий ТЗ 11).

Экран утверждён заказчиком 29.09.2026 (`frontend/src/sections/management/`); допущения —
V20–V25 в `docs/OPEN-QUESTIONS.md`.

**Обход** (ТЗ 7) — очередь того, где данные могли отстать от жизни: у пункта причина и
два-три действия, каждое меняет данные; кнопки «всё нормально» нет. Очередь считается из
данных, а не хранится: пункт уходит, когда данные поправлены. Одна запись — один пункт:
просроченная задача на проверке стоит в очереди один раз, по первой причине в порядке
`RoundReason` (V20) — одно действие отвечает сразу на обе.
"""

from __future__ import annotations

import re
from datetime import date, time, timedelta
from enum import StrEnum
from typing import Any

from app.domain.dictionaries import SettingKey, TaskStatus
from app.domain.errors import RuleViolationError
from app.domain.push import LAST_SUMMARY_RUN, SUMMARY_WINDOW


class RoundReason(StrEnum):
    """Почему запись в обходе. Порядок — порядок очереди и приоритет при совпадении."""

    DECISION_OVERDUE = "decision_overdue"
    TASK_OVERDUE = "task_overdue"
    MILESTONE_PASSED = "milestone_passed"
    TASK_REVIEW = "task_review"
    IMPEDIMENT_STALE = "impediment_stale"
    PROJECT_SILENT = "project_silent"
    TASK_UNASSIGNED = "task_unassigned"

    @property
    def rank(self) -> int:
        return list(RoundReason).index(self)


class RoundAction(StrEnum):
    """Действие обхода в одно касание. Каждое меняет данные (ТЗ 7)."""

    DECISION_DONE = "decision_done"
    TASK_DONE = "task_done"
    TASK_CANCEL = "task_cancel"
    TASK_BACK = "task_back"
    MOVE_WEEK = "move_week"
    MILESTONE_PASSED = "milestone_passed"
    IMPEDIMENT_CONFIRM = "impediment_confirm"
    IMPEDIMENT_CLEAR = "impediment_clear"
    NOTE = "note"
    HOLD = "hold"
    PROJECT_DONE = "project_done"
    ASSIGN = "assign"


class RecordKind(StrEnum):
    """Запись, которую меняет действие обхода."""

    DECISION = "decision"
    TASK = "task"
    MILESTONE = "milestone"
    PROJECT = "project"


NEEDS_INPUT = frozenset({RoundAction.NOTE, RoundAction.HOLD, RoundAction.ASSIGN})
"""Действия со строкой или выбором: «что мешает», причина паузы, ответственный."""

MOVE_DAYS = 7
"""«Перенести на неделю» — неделя от сегодня, а не от прошедшего срока (V20): срок,
прошедший девять дней назад, плюс неделя — всё ещё прошедший, и пункт остался бы в
обходе после того, как по нему уже приняли решение."""

RECORD_OF: dict[RoundReason, RecordKind] = {
    RoundReason.DECISION_OVERDUE: RecordKind.DECISION,
    RoundReason.TASK_OVERDUE: RecordKind.TASK,
    RoundReason.MILESTONE_PASSED: RecordKind.MILESTONE,
    RoundReason.TASK_REVIEW: RecordKind.TASK,
    RoundReason.IMPEDIMENT_STALE: RecordKind.PROJECT,
    RoundReason.PROJECT_SILENT: RecordKind.PROJECT,
    RoundReason.TASK_UNASSIGNED: RecordKind.TASK,
}


def actions_for(reason: RoundReason, *, task_status: TaskStatus | None = None) -> list[RoundAction]:
    """Действия пункта — в порядке кнопок; первое — главное.

    У новой задачи «сделана» нет: граф переходов не пускает «новая → готова» (утверждённый
    экран «Задачи»), и кнопка, которая отвечает отказом, хуже отсутствующей.
    """
    if reason is RoundReason.DECISION_OVERDUE:
        return [RoundAction.DECISION_DONE, RoundAction.MOVE_WEEK]
    if reason is RoundReason.TASK_OVERDUE:
        head = [] if task_status is TaskStatus.NEW else [RoundAction.TASK_DONE]
        return [*head, RoundAction.MOVE_WEEK, RoundAction.TASK_CANCEL]
    if reason is RoundReason.MILESTONE_PASSED:
        return [RoundAction.MILESTONE_PASSED, RoundAction.MOVE_WEEK]
    if reason is RoundReason.TASK_REVIEW:
        return [RoundAction.TASK_DONE, RoundAction.TASK_BACK]
    if reason is RoundReason.IMPEDIMENT_STALE:
        return [RoundAction.IMPEDIMENT_CONFIRM, RoundAction.IMPEDIMENT_CLEAR, RoundAction.NOTE]
    if reason is RoundReason.PROJECT_SILENT:
        return [RoundAction.NOTE, RoundAction.PROJECT_DONE, RoundAction.HOLD]
    return [RoundAction.ASSIGN, RoundAction.TASK_CANCEL]


def moved_due(today: date) -> date:
    return today + timedelta(days=MOVE_DAYS)


def week_start(today: date) -> date:
    """Понедельник недели обхода — неделя в Узбекистане начинается с понедельника."""
    return today - timedelta(days=today.weekday())


def clean_input(action: RoundAction, value: str | None) -> str:
    """Строка действия: «что мешает» и причина паузы — непустые; ответственный — выбран."""
    text = (value or "").strip()
    if action in NEEDS_INPUT and not text:
        raise RuleViolationError(
            {
                RoundAction.NOTE: "Напишите, что мешает",
                RoundAction.HOLD: "Напишите причину паузы",
                RoundAction.ASSIGN: "Выберите ответственного",
            }[action]
        )
    return text


# --------------------------------------------------------------------------------------
# Пороги
# --------------------------------------------------------------------------------------


class ThresholdOrigin(StrEnum):
    """Откуда значение по умолчанию: названо в ТЗ или принято допущением."""

    TZ = "tz"
    ASSUMPTION = "assumption"


THRESHOLD_DEFAULTS: dict[SettingKey, tuple[int | str, ThresholdOrigin]] = {
    SettingKey.BURN_DAYS: (7, ThresholdOrigin.TZ),
    SettingKey.QUIET_DAYS: (14, ThresholdOrigin.TZ),
    SettingKey.IMPEDIMENT_STALE_DAYS: (14, ThresholdOrigin.ASSUMPTION),
    SettingKey.MIN_CLOSED_FOR_PACE: (10, ThresholdOrigin.TZ),
    SettingKey.HOT_DAY_THRESHOLD: (3, ThresholdOrigin.ASSUMPTION),
    SettingKey.HOT_WINDOW_DAYS: (28, ThresholdOrigin.ASSUMPTION),
    SettingKey.SUMMARY_AT: ("08:30", ThresholdOrigin.TZ),
}
"""Значения по умолчанию — не справочник, а факт ТЗ и допущений (V15): к ним возвращаются
одним касанием, и сам справочник их не хранит. Текущие значения — в таблице `settings`."""

_TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def clean_threshold(*, value_type: str, value: Any, low: int | None, high: int | None) -> Any:
    """Значение порога: время — «ЧЧ:ММ», дни и счёт — целое в границах справочника.

    Порог-время один — время утренней сводки, и принимается оно только внутри окна
    `app.domain.push.SUMMARY_WINDOW`: там же сказано, почему окно кончается раньше
    последнего вызова расписания. Время вне окна сохранилось бы и не наступило либо
    оставило бы сводке одну попытку.
    """
    if value_type == "time":
        if not isinstance(value, str) or not _TIME.fullmatch(value):
            raise RuleViolationError("Время — часы и минуты, например 08:30")
        start, end = SUMMARY_WINDOW
        if not start <= time.fromisoformat(value) <= end:
            raise RuleViolationError(
                f"Сводку можно назначить с {start:%H:%M} до {end:%H:%M}: расписание "
                f"повторяет попытки только до {LAST_SUMMARY_RUN:%H:%M}, и более позднему "
                "времени не осталось бы запаса на повтор"
            )
        return value
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuleViolationError("Порог — целое число")
    if (low is not None and value < low) or (high is not None and value > high):
        raise RuleViolationError(f"Порог — целое число от {low} до {high}")
    return value


def threshold_bounds(
    *, value_type: str, low: int | None, high: int | None
) -> tuple[int | str | None, int | str | None]:
    """Границы порога для экрана — те же, что проверяет `clean_threshold`.

    У чисел они в справочнике, у времени — окно сводки, и едут они строками «ЧЧ:ММ»:
    экран ставит их полю времени и не даёт записать то, что сервер всё равно отвергнет.
    """
    if value_type == "time":
        start, end = SUMMARY_WINDOW
        return f"{start:%H:%M}", f"{end:%H:%M}"
    return low, high


# --------------------------------------------------------------------------------------
# Справочники
# --------------------------------------------------------------------------------------


class DictionaryKind(StrEnum):
    """Справочник Управления — в порядке списка на экране (ТЗ 3.9)."""

    PROJECT_TYPES = "project_types"
    TASK_TYPES = "task_types"
    DIRECTIONS = "directions"
    REGIONS = "regions"
    PROJECT_STATUSES = "project_statuses"
    TASK_STATUSES = "task_statuses"
    ORGANIZATIONS = "organizations"

    @property
    def can_add(self) -> bool:
        """Набор статусов задан графом переходов, регионов — ТЗ 3.1; остальное дополняется."""
        return self in (
            DictionaryKind.PROJECT_TYPES,
            DictionaryKind.TASK_TYPES,
            DictionaryKind.DIRECTIONS,
            DictionaryKind.ORGANIZATIONS,
        )

    @property
    def can_disable(self) -> bool:
        """Статус не выключается: на нём правила переходов и терминальность."""
        return self not in (DictionaryKind.PROJECT_STATUSES, DictionaryKind.TASK_STATUSES)

    @property
    def can_move(self) -> bool:
        """Организации идут по названию: ручной порядок в списке из сотни ведомств ничего не
        говорит, и столбца порядка у них нет."""
        return self is not DictionaryKind.ORGANIZATIONS


NAME_MAX_LENGTH = 200
"""Как у столбцов `name_*` справочников."""

TEMPLATE_OFFSET_MAX = 3650
"""Веха шаблона — не дальше десяти лет от начала проекта: дальше — опечатка."""


def clean_name(name: str, *, limit: int = NAME_MAX_LENGTH) -> str:
    if "\x00" in name:
        raise RuleViolationError("В названии есть недопустимый символ")
    value = name.strip()
    if not value:
        raise RuleViolationError("Напишите название")
    if len(value) > limit:
        raise RuleViolationError(f"Название длиннее {limit} символов")
    return value


def renamed_script(*, old_ru: str, current: str, new_ru: str) -> str:
    """Узбекское название после переименования по-русски (V22).

    Повторяло русское — повторяет и новое: перевода не было, и прежнее русское слово в
    узбекской версии было бы ошибкой. Было переведено — остаётся: переводчик правит его
    сам, вместе с языками в блоке 3.
    """
    return new_ru if current == old_ru else current


def clean_offset(offset: int) -> int:
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise RuleViolationError("Через сколько дней — целое число")
    if not 0 <= offset <= TEMPLATE_OFFSET_MAX:
        raise RuleViolationError(f"Через сколько дней — от 0 до {TEMPLATE_OFFSET_MAX}")
    return offset
