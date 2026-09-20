"""Обработчики задач по расписанию.

Три задачи, каждая со своим периодом:

| Имя | Период | Когда зовут | Что делает |
|---|---|---|---|
| `morning-summary` | сутки | 08:30 Ташкент | собирает утреннюю сводку руководителю |
| `daily-snapshot` | сутки | 23:50 Ташкент | сохраняет состояние дня для графиков |
| `deadline-check` | час | в рабочие часы | считает, что просрочено и что подходит к сроку |

**Числа берутся у сервиса показателей и больше нигде.** Это инвариант 2: сводка,
пришедшая в 08:30, обязана совпадать с тем, что руководитель увидит на Пульте, открыв
телефон в 08:31. Свой запрос здесь означал бы второй расчёт — и расхождение, которое
обнаружится ровно в тот момент, когда на него посмотрят вдвоём.

**Чего эти обработчики пока не делают.** Отправки нет: порт `PushSender` появляется вместе
с устройствами и подписками, и до него сводка складывается в результат прогона — её видно
в журнале прогонов и в сводке GitHub Actions. Это не заглушка: числа настоящие, считает их
тот же код, который потом будет их отправлять.
"""

from __future__ import annotations

from typing import Any

from app.domain.attention import Attention
from app.jobs.registry import Job, JobContext, daily_period, hourly_period, register
from app.services import metrics


async def _summary(context: JobContext) -> dict[str, Any]:
    """Лестница внимания в виде чисел — основа и сводки, и снимка, и проверки сроков."""
    # Сегодняшний день — по Ташкенту: просрочка считается по календарным дням
    # (инвариант 8), иначе работа становится просроченной в пять утра по местному времени.
    today = context.now.astimezone(context.timezone).date()
    ladder = await metrics.ladder(context.session, today=today)

    return {
        "local_date": today.isoformat(),
        "needs_attention": ladder.needs_attention,
        "awaiting_decision": ladder.count(Attention.AWAITING_DECISION),
        "overdue": ladder.count(Attention.OVERDUE),
        "burning": ladder.count(Attention.BURNING),
        "blocked_by_others": ladder.count(Attention.BLOCKED_BY_OTHERS),
        "silent": ladder.count(Attention.SILENT),
        "on_track": ladder.on_track,
    }


async def morning_summary(context: JobContext) -> dict[str, Any]:
    """Утренняя сводка: что ждёт решения и что горит сегодня (ТЗ 8).

    Отправка появится вместе с портом `PushSender`. До неё сводка лежит в результате
    прогона — руководитель её ещё не получает, и отчёт блока говорит об этом прямо, а не
    «уведомления готовы».
    """
    return {**await _summary(context), "delivered": False}


async def daily_snapshot(context: JobContext) -> dict[str, Any]:
    """Состояние на конец дня — основа графиков «как менялось».

    Догоняющий режим обеспечен самим периодом: пропущенные сутки остаются без записи, и
    это видно по списку прогонов, а не выясняется из несходящегося графика.
    """
    return await _summary(context)


async def deadline_check(context: JobContext) -> dict[str, Any]:
    """Проверка сроков: что уже просрочено и что подходит к сроку.

    Просрочка не пишется в статус и не хранится (инвариант 1) — задача её только считает.
    Напоминания появятся вместе с уведомлениями.
    """
    return await _summary(context)


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
