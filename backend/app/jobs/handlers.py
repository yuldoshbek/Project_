"""Обработчики задач по расписанию.

Три задачи, каждая со своим периодом:

| Имя | Период | Когда зовут | Что делает |
|---|---|---|---|
| `morning-summary` | сутки | 06:00–11:50 Ташкент, раз в 10 мин | отправляет сводку в её время |
| `daily-snapshot` | сутки | 23:50 Ташкент | сохраняет состояние дня для графиков |
| `deadline-check` | час | в рабочие часы | считает, что просрочено и что подходит к сроку |

**Числа берутся у сервиса показателей и больше нигде.** Это инвариант 2: сводка,
пришедшая в 08:30, обязана совпадать с тем, что руководитель увидит на Пульте, открыв
телефон в 08:31. Свой запрос здесь означал бы второй расчёт — и расхождение, которое
обнаружится ровно в тот момент, когда на него посмотрят вдвоём.

**Сводку зовут часто, а работает она раз в день.** Время сводки — порог справочника, его
меняет помощник без выкладки (V24), а строку cron меняет только выкладка. Поэтому
расписание спрашивает каждые десять минут, и день занимает только доставленная сводка:
после неё остальные вызовы до 11:50 отвечают «уже сделано» одним запросом. До того —
`not_due` с причиной, и строки о прогоне нет: «ещё не время» (`not_yet`), «некому»
(`no_device` — руководитель не включил уведомления или служба отключила все его
устройства), «нечем» (`not_configured` — нет ключа). Служба не приняла сводку ни для одного
устройства — прогон `failed`, ответ 503, и следующий вызов пробует снова.
"""

from __future__ import annotations

from typing import Any

from app.domain.attention import Attention
from app.domain.push import SummaryOutcome
from app.jobs.registry import (
    STATUS_FAILED,
    STATUS_NOT_DUE,
    Job,
    JobContext,
    Release,
    daily_period,
    hourly_period,
    register,
)
from app.services import metrics, summary


async def _summary(context: JobContext) -> dict[str, Any]:
    """Лестница внимания в виде чисел — основа и сводки, и снимка, и проверки сроков."""
    # Сегодняшний день — по Ташкенту: просрочка считается по календарным дням
    # (инвариант 8), иначе работа становится просроченной в пять утра по местному времени.
    today = context.now.astimezone(context.timezone).date()
    ladder = await metrics.ladder(context.session, today=today, zone=context.timezone)

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


async def morning_summary(context: JobContext) -> dict[str, Any] | Release:
    """Утренняя сводка: что ждёт решения и что со сроком сегодня (ТЗ 8, V26).

    В результате прогона — те же числа лестницы, что у снимка, и исход отправки: он виден
    в журнале прогонов и в сводке прогона GitHub Actions — там и ищут ответ на «почему не
    пришла».

    День занимает только доставка. «Некому» — все устройства руководителя отключены
    службой — отпускает день, как «ещё не время»: сводка уйдёт, когда он включит
    уведомления снова. «Служба не приняла» отпускает его неудачей — 503, и расписание
    повторит попытку. Записанное прогоном остаётся в обоих случаях (`Release`).
    """
    numbers = await _summary(context)
    sent = await summary.send(context.session, context.push, now=context.now, zone=context.timezone)
    result = {
        **numbers,
        "delivered": sent.delivered,
        "devices": sent.devices,
        "reason": sent.reason.value,
    }
    if sent.reason is SummaryOutcome.SENT:
        return result
    if sent.reason is SummaryOutcome.REFUSED:
        return Release(
            status=STATUS_FAILED,
            result=result,
            error="Сводка не доставлена: служба уведомлений не приняла её ни для одного "
            "устройства. Расписание повторит попытку",
        )
    return Release(status=STATUS_NOT_DUE, result=result)


async def summary_is_due(context: JobContext) -> str | None:
    """Пора ли сводке: время наступило, ключ есть, руководителю есть куда её доставить
    (V24). Не пора — причина из `SummaryOutcome`."""
    reason = await summary.blocker(
        context.session, context.push, now=context.now, zone=context.timezone
    )
    return None if reason is None else reason.value


async def daily_snapshot(context: JobContext) -> dict[str, Any]:
    """Состояние на конец дня — основа графиков «как менялось».

    Догоняющий режим обеспечен самим периодом: пропущенные сутки остаются без записи, и
    это видно по списку прогонов, а не выясняется из несходящегося графика.
    """
    return await _summary(context)


async def deadline_check(context: JobContext) -> dict[str, Any]:
    """Проверка сроков: что уже просрочено и что подходит к сроку.

    Просрочка не пишется в статус и не хранится (инвариант 1) — задача её только считает.
    Напоминаний о сроках она не шлёт: ТЗ v2.0 их сняло, поводов для пуша два — утренняя
    сводка и вопрос помощника (ADR-0036).
    """
    return await _summary(context)


register(
    Job(
        name="morning-summary",
        title="Утренняя сводка",
        period=daily_period,
        handler=morning_summary,
        due=summary_is_due,
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
