"""Обработчики задач по расписанию.

Три задачи, каждая со своим периодом:

| Имя | Период | Когда зовут | Что делает |
|---|---|---|---|
| `morning-summary` | сутки | 08:30 Ташкент | собирает утреннюю сводку руководителю |
| `daily-snapshot` | сутки | 23:50 Ташкент | сохраняет состояние дня для графиков |
| `deadline-check` | час | каждый час | считает, что просрочено и что подходит к сроку |

**Чего эти обработчики пока не делают.** Отправки нет: порт `PushSender` появляется в
блоке 1 вместе с устройствами и подписками, и до него сводка складывается в результат
прогона — её видно в журнале прогонов и в сводке GitHub Actions. Это не заглушка: числа
настоящие, считает их тот же код, который потом будет их отправлять. Отдельной таблицы
снимков тоже нет — до неё состояние дня живёт в `job_runs.result`, потому что заводить
таблицу под графики, которых ещё нет, значит заводить поля «на будущее» (инвариант 14).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from app.domain.dictionaries import ProjectStatus
from app.jobs.registry import Job, JobContext, daily_period, hourly_period, register
from app.repos.models import Project, Task
from app.services.tasks import overdue_condition

# Сколько дней считается «подходит к сроку». Значение по умолчанию совпадает с настройкой
# ORBITA_WARN_DAYS; в рабочей системе порог живёт в справочнике и меняется без выкладки.
SOON_DAYS = 3

PROJECT_TERMINAL = [status.value for status in ProjectStatus if status.is_terminal]


async def _counts(context: JobContext) -> dict[str, Any]:
    """Числа, из которых собираются и сводка, и снимок дня, и проверка сроков.

    Один запрос на всех — то же правило, что у показателей на экранах: «просрочено»
    считает один код, иначе Пульт и раздел расходятся (CLAUDE.md, инварианты 1 и 2).
    """
    session = context.session
    now = context.now
    soon = now + timedelta(days=SOON_DAYS)

    overdue_tasks = await session.scalar(
        select(func.count()).select_from(Task).where(overdue_condition(now))
    )
    soon_tasks = await session.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            Task.due_at.is_not(None),
            Task.due_at >= now,
            Task.due_at < soon,
            ~overdue_condition(now),
        )
    )
    # У проекта срок — дата, а не момент: «просрочено» считается по календарным дням в
    # Ташкенте, иначе проект становится просроченным в пять утра по местному времени.
    today = now.astimezone(context.timezone).date()
    overdue_projects = await session.scalar(
        select(func.count())
        .select_from(Project)
        .where(
            Project.due_on < today,
            Project.status_code.notin_(PROJECT_TERMINAL),
        )
    )
    active_projects = await session.scalar(
        select(func.count())
        .select_from(Project)
        .where(Project.status_code.notin_(PROJECT_TERMINAL))
    )

    return {
        "overdue_tasks": int(overdue_tasks or 0),
        "tasks_due_soon": int(soon_tasks or 0),
        "overdue_projects": int(overdue_projects or 0),
        "active_projects": int(active_projects or 0),
    }


async def morning_summary(context: JobContext) -> dict[str, Any]:
    """Утренняя сводка: что требует внимания на начало дня.

    Отправка появится вместе с портом `PushSender` в блоке 1. До неё сводка лежит в
    результате прогона — руководитель её ещё не получает, и отчёт блока 0 говорит об этом
    прямо, а не «уведомления готовы».
    """
    counts = await _counts(context)
    return {
        **counts,
        "local_date": context.now.astimezone(context.timezone).strftime("%Y-%m-%d"),
        "delivered": False,
    }


async def daily_snapshot(context: JobContext) -> dict[str, Any]:
    """Состояние на конец дня — основа графиков «как менялось».

    Догоняющий режим обеспечен самим периодом: пропущенные сутки остаются без записи, и
    это видно по списку прогонов, а не выясняется из несходящегося графика.
    """
    counts = await _counts(context)
    return {**counts, "local_date": context.now.astimezone(context.timezone).strftime("%Y-%m-%d")}


async def deadline_check(context: JobContext) -> dict[str, Any]:
    """Проверка сроков: что уже просрочено и что подходит к сроку.

    Просрочка не пишется в статус и не хранится (инвариант 1) — задача её только считает.
    Напоминания появятся вместе с уведомлениями в блоке 1.
    """
    counts = await _counts(context)
    return {**counts, "soon_days": SOON_DAYS}


register(
    Job(
        name="morning-summary",
        title="Утренняя сводка",
        period=daily_period,
        handler=morning_summary,
    )
)
register(
    Job(
        name="daily-snapshot",
        title="Снимок состояния за день",
        period=daily_period,
        handler=daily_snapshot,
    )
)
register(
    Job(
        name="deadline-check",
        title="Проверка сроков",
        period=hourly_period,
        handler=deadline_check,
    )
)
