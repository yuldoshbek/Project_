"""Коды справочников, от которых зависит поведение системы.

Здесь разрешается противоречие, заложенное в ТЗ. Раздел 6.8 требует, чтобы справочники
менялись без разработчика; разделы 6.4 и 6.5 требуют, чтобы система понимала смысл
статусов — считала просрочку, светофор, показывала руководителю то, что ждёт его решения.
Полностью редактируемый справочник этого не позволяет: смысл нового значения системе
неоткуда взять.

Разделение такое:

- **код принадлежит коду** — перечисления ниже, на них опирается логика;
- **название, порядок, цвет и видимость принадлежат данным** — таблицы справочников,
  помощник меняет их в интерфейсе.

Практическое следствие: переименовать «На контроле руководителя» можно из интерфейса и
на всех трёх письменностях; завести седьмой статус проекта — нельзя, потому что системе
неоткуда узнать, что он означает. Это ограничение названо вслух в OPEN-QUESTIONS.
"""

from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    """Статусы проекта (ТЗ 7)."""

    INITIATION = "initiation"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    AWAITING_DECISION = "awaiting_decision"
    DONE = "done"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Работа по проекту закончена — в светофоре он не участвует (ADR-0005)."""
        return self in {ProjectStatus.DONE, ProjectStatus.CANCELLED}

    @property
    def requires_reason(self) -> bool:
        """ТЗ 7 требует указывать причину при паузе и отмене."""
        return self in {ProjectStatus.ON_HOLD, ProjectStatus.CANCELLED}


class TaskStatus(StrEnum):
    """Статусы задачи.

    «Просрочена» из ТЗ 7 здесь намеренно отсутствует: это не состояние работы, а
    следствие наступившего срока, и вычисляется оно отдельно (ADR-0004).
    В интерфейсе пользователь по-прежнему видит «Просрочена» — как признак и как
    значение фильтра.
    """

    NEW = "new"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {TaskStatus.DONE, TaskStatus.CANCELLED}


class Priority(StrEnum):
    """Приоритеты (ТЗ 7)."""

    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class OrganizationKind(StrEnum):
    """Виды организаций-партнёров.

    Мандат агентства включает международное сотрудничество (ТЗ 3.1), поэтому зарубежные
    партнёры — не частный случай, а отдельный вид.
    """

    MINISTRY = "ministry"
    AGENCY = "agency"
    UNIVERSITY = "university"
    COMPANY = "company"
    INTERNATIONAL = "international"


class Health(StrEnum):
    """Светофор актуальности (ТЗ 6.4, ADR-0005).

    Серый — не «нет данных», а «из светофора исключён»: завершённые и отменённые проекты.
    Без него доля зелёного росла бы по мере завершения работ и перестала бы что-либо значить.
    """

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    GREY = "grey"


class SettingKey(StrEnum):
    """Ключи настраиваемых параметров.

    Значения живут в таблице и меняются помощником; ключи известны коду, иначе некому
    было бы их прочитать.
    """

    WARN_DAYS = "warn_days"
    WARN_RATIO = "warn_ratio"
    STAGNATION_DAYS = "stagnation_days"
    REMINDER_DAYS = "reminder_days"
    QUIET_HOURS_START = "quiet_hours_start"
    QUIET_HOURS_END = "quiet_hours_end"
    DIGEST_AT = "digest_at"
    MAX_UPLOAD_MB = "max_upload_mb"
