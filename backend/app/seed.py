"""Наполнение справочников значениями из раздела 7 ТЗ.

Запуск: `make seed` (или `python -m app.seed`).

**Существующие записи не изменяются.** Помощник вправе переименовать статус или поменять
порядок (ТЗ 6.8); повторный запуск сидов, затирающий его правки, превратил бы
редактируемый справочник в декорацию. Добавляются только отсутствующие значения — это
делает команду безопасной после обновления системы.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import structlog
from sqlalchemy import CursorResult
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dictionaries import (
    Priority,
    ProjectStatus,
    SettingKey,
    TaskStatus,
)
from app.observability import configure_logging
from app.repos.database import dispose_database, init_database, session_scope
from app.repos.models import (
    Direction,
    PriorityRef,
    ProjectStatusRef,
    Setting,
    TaskStatusRef,
)
from app.settings import get_settings

logger = structlog.get_logger(__name__)

# Направления из мандата агентства (ТЗ 7, стартовый набор).
DIRECTIONS: list[dict[str, Any]] = [
    {
        "code": "space_monitoring",
        "name_ru": "Космический мониторинг",
        "name_uz_cyrl": "Космик мониторинг",
        "name_uz_latn": "Kosmik monitoring",
        "sort_order": 10,
    },
    {
        "code": "remote_sensing",
        "name_ru": "Дистанционное зондирование Земли",
        "name_uz_cyrl": "Ерни масофадан зондлаш",
        "name_uz_latn": "Yerni masofadan zondlash",
        "sort_order": 20,
    },
    {
        "code": "international",
        "name_ru": "Международное сотрудничество",
        "name_uz_cyrl": "Халқаро ҳамкорлик",
        "name_uz_latn": "Xalqaro hamkorlik",
        "sort_order": 30,
    },
    {
        "code": "infrastructure",
        "name_ru": "Инфраструктура и техническое развитие",
        "name_uz_cyrl": "Инфратузилма ва техник ривожланиш",
        "name_uz_latn": "Infratuzilma va texnik rivojlanish",
        "sort_order": 40,
    },
    {
        "code": "regulatory",
        "name_ru": "Нормативно-регуляторная работа",
        "name_uz_cyrl": "Меъёрий-тартибга солиш ишлари",
        "name_uz_latn": "Meʼyoriy-tartibga solish ishlari",
        "sort_order": 50,
    },
    {
        "code": "internal",
        "name_ru": "Внутренние организационные инициативы",
        "name_uz_cyrl": "Ички ташкилий ташаббуслар",
        "name_uz_latn": "Ichki tashkiliy tashabbuslar",
        "sort_order": 60,
    },
]

PROJECT_STATUSES: list[dict[str, Any]] = [
    {
        "code": ProjectStatus.INITIATION,
        "name_ru": "Инициация",
        "name_uz_cyrl": "Бошланиш",
        "name_uz_latn": "Boshlanish",
        "color": "grey",
        "sort_order": 10,
    },
    {
        "code": ProjectStatus.IN_PROGRESS,
        "name_ru": "В работе",
        "name_uz_cyrl": "Ишда",
        "name_uz_latn": "Ishda",
        "color": "blue",
        "sort_order": 20,
    },
    {
        "code": ProjectStatus.ON_HOLD,
        "name_ru": "Приостановлен",
        "name_uz_cyrl": "Тўхтатилган",
        "name_uz_latn": "Toʻxtatilgan",
        "color": "amber",
        "requires_reason": True,
        "sort_order": 30,
    },
    {
        "code": ProjectStatus.AWAITING_DECISION,
        "name_ru": "На контроле руководителя",
        "name_uz_cyrl": "Раҳбар назоратида",
        "name_uz_latn": "Rahbar nazoratida",
        "color": "violet",
        "sort_order": 40,
    },
    {
        "code": ProjectStatus.DONE,
        "name_ru": "Завершён",
        "name_uz_cyrl": "Якунланган",
        "name_uz_latn": "Yakunlangan",
        "color": "green",
        "is_terminal": True,
        "sort_order": 50,
    },
    {
        "code": ProjectStatus.CANCELLED,
        "name_ru": "Отменён",
        "name_uz_cyrl": "Бекор қилинган",
        "name_uz_latn": "Bekor qilingan",
        "color": "grey",
        "is_terminal": True,
        "requires_reason": True,
        "sort_order": 60,
    },
]

# «Просрочена» из ТЗ 7 здесь отсутствует намеренно: это вычисляемый признак,
# а не состояние работы (ADR-0004). В интерфейсе она есть — как маркер и как фильтр.
TASK_STATUSES: list[dict[str, Any]] = [
    {
        "code": TaskStatus.NEW,
        "name_ru": "Новая",
        "name_uz_cyrl": "Янги",
        "name_uz_latn": "Yangi",
        "color": "grey",
        "sort_order": 10,
    },
    {
        "code": TaskStatus.IN_PROGRESS,
        "name_ru": "В работе",
        "name_uz_cyrl": "Ишда",
        "name_uz_latn": "Ishda",
        "color": "blue",
        "sort_order": 20,
    },
    {
        "code": TaskStatus.IN_REVIEW,
        "name_ru": "На проверке",
        "name_uz_cyrl": "Текширувда",
        "name_uz_latn": "Tekshiruvda",
        "color": "violet",
        "sort_order": 30,
    },
    {
        "code": TaskStatus.DONE,
        "name_ru": "Выполнена",
        "name_uz_cyrl": "Бажарилган",
        "name_uz_latn": "Bajarilgan",
        "color": "green",
        "is_terminal": True,
        "sort_order": 40,
    },
    {
        "code": TaskStatus.CANCELLED,
        "name_ru": "Отменена",
        "name_uz_cyrl": "Бекор қилинган",
        "name_uz_latn": "Bekor qilingan",
        "color": "grey",
        "is_terminal": True,
        "sort_order": 50,
    },
]

PRIORITIES: list[dict[str, Any]] = [
    {
        "code": Priority.URGENT,
        "name_ru": "Срочно",
        "name_uz_cyrl": "Шошилинч",
        "name_uz_latn": "Shoshilinch",
        "color": "red",
        # Ноль по ADR-0005: срочная задача жёлтая с момента постановки и красная сразу
        # после срока. Значение, а не условие в коде, — помощник может его поправить.
        "warn_days_override": 0,
        "sort_order": 10,
    },
    {
        "code": Priority.HIGH,
        "name_ru": "Высокий",
        "name_uz_cyrl": "Юқори",
        "name_uz_latn": "Yuqori",
        "color": "amber",
        "sort_order": 20,
    },
    {
        "code": Priority.NORMAL,
        "name_ru": "Обычный",
        "name_uz_cyrl": "Оддий",
        "name_uz_latn": "Oddiy",
        "color": "blue",
        "sort_order": 30,
    },
    {
        "code": Priority.LOW,
        "name_ru": "Низкий",
        "name_uz_cyrl": "Паст",
        "name_uz_latn": "Past",
        "color": "grey",
        "sort_order": 40,
    },
]

SETTINGS: list[dict[str, Any]] = [
    {
        "key": SettingKey.WARN_DAYS,
        "value": 3,
        "value_type": "days",
        "min_value": 0,
        "max_value": 60,
        "description_ru": "За сколько дней до срока проект становится жёлтым (ADR-0005)",
    },
    {
        "key": SettingKey.WARN_RATIO,
        "value": 0.8,
        "value_type": "ratio",
        "description_ru": "Доля израсходованного срока, после которой проект жёлтый",
    },
    {
        "key": SettingKey.STAGNATION_DAYS,
        "value": 14,
        "value_type": "days",
        "min_value": 1,
        "max_value": 180,
        "description_ru": (
            "Сколько дней без изменения процента выполнения считается застоем. "
            "Такой проект может быть зелёным и потому невидимым на светофоре (ADR-0014)"
        ),
    },
    {
        "key": SettingKey.REMINDER_DAYS,
        "value": [1, 3, 7],
        "value_type": "days_list",
        "description_ru": "За сколько дней до срока напоминать (ТЗ 6.5)",
    },
    {
        "key": SettingKey.QUIET_HOURS_START,
        "value": "20:00",
        "value_type": "time",
        "description_ru": "С какого часа уведомления откладываются до утра",
    },
    {
        "key": SettingKey.QUIET_HOURS_END,
        "value": "08:00",
        "value_type": "time",
        "description_ru": "С какого часа уведомления снова отправляются",
    },
    {
        "key": SettingKey.DIGEST_AT,
        "value": "08:30",
        "value_type": "time",
        "description_ru": "Время утренней сводки руководителю в Telegram (ADR-0013)",
    },
    {
        "key": SettingKey.MAX_UPLOAD_MB,
        "value": 50,
        "value_type": "megabytes",
        "min_value": 1,
        "max_value": 500,
        "description_ru": "Предельный размер вложения (ADR-0009)",
    },
]


async def _insert_missing(
    session: AsyncSession,
    model: type[Any],
    rows: list[dict[str, Any]],
    key_column: str,
) -> int:
    """Добавляет отсутствующие строки, не трогая существующие.

    `ON CONFLICT DO NOTHING` — не оптимизация, а требование: правки помощника в
    справочниках должны переживать обновление системы.

    Строки вставляются по одной, а не пачкой: у них разный набор полей (у одних есть
    `requires_reason`, у других нет), и групповая вставка потребовала бы приводить их
    к общему виду, подставляя значения по умолчанию руками — мимо тех, что объявлены
    в модели.
    """
    added = 0
    for row in rows:
        values = {**row, key_column: str(row[key_column])}
        statement = (
            insert(model).values(**values).on_conflict_do_nothing(index_elements=[key_column])
        )
        result = cast("CursorResult[Any]", await session.execute(statement))
        added += result.rowcount or 0
    return added


async def seed(session: AsyncSession) -> dict[str, int]:
    """Наполняет справочники. Возвращает число добавленных записей по каждому."""
    added = {
        "directions": await _insert_missing(session, Direction, DIRECTIONS, "code"),
        "project_statuses": await _insert_missing(
            session, ProjectStatusRef, PROJECT_STATUSES, "code"
        ),
        "task_statuses": await _insert_missing(session, TaskStatusRef, TASK_STATUSES, "code"),
        "priorities": await _insert_missing(session, PriorityRef, PRIORITIES, "code"),
        "settings": await _insert_missing(session, Setting, SETTINGS, "key"),
    }
    await session.flush()
    return added


async def _run() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.use_json_logs)
    init_database(settings)
    try:
        async for session in session_scope():
            added = await seed(session)
    finally:
        await dispose_database()

    if any(added.values()):
        logger.info("seed_completed", added=added)
    else:
        logger.info("seed_completed", added=added, note="всё уже на месте")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
