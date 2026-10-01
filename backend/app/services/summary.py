"""Утренняя сводка руководителю: вкладка «Сводка» Пульта и пуш, который она показывает (ТЗ 8).

Экран утверждён заказчиком 29.09.2026 (`frontend/src/sections/pult/Summary.tsx`), и одна
сборка здесь отвечает обоим: `load` отдаёт экрану то, что уйдёт на телефон, а `send`
отправляет ровно это. Экран блокировки собирает одна функция — `lock_screen`, — и
предпросмотр совпадает с пушем по построению, а не по договорённости.

Числа и строки — из лестницы `app.services.metrics` (инвариант 2): «ждёт решения» — её
ступень, «срок сегодня» — её правило `due_today` (V26).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.push import PushSender
from app.domain.attention import Attention
from app.domain.clock import local_date
from app.domain.dictionaries import SettingKey
from app.domain.management import THRESHOLD_DEFAULTS
from app.domain.push import (
    LAST_SUMMARY_RUN,
    PUSH_FIELD_LENGTH,
    NotificationKind,
    SummaryOutcome,
    preview,
    summary_blocker,
    summary_key,
    summary_payload,
)
from app.repos import notifications as repo
from app.services import metrics, notifications
from app.services.dictionaries import get_setting
from app.services.pult import RowView, row_views

DEFAULT_SEND_AT = str(THRESHOLD_DEFAULTS[SettingKey.SUMMARY_AT][0])


@dataclass(frozen=True, slots=True)
class PushRow:
    """Строка на экране блокировки — ровно то, из чего интерфейс собирает её фразу."""

    title: str | None
    section: str
    decision_kind: str | None
    context: str | None
    deviation: int


@dataclass(frozen=True, slots=True)
class AwaitingLine:
    count: int
    oldest: PushRow


@dataclass(frozen=True, slots=True)
class DueLine:
    count: int
    first: PushRow


@dataclass(frozen=True, slots=True)
class LockScreen:
    """Что покажет экран блокировки: два числа и две строки. Пустой пункт — `None`,
    а фразу «решений не ждёт» подставляет интерфейс (V29)."""

    awaiting: AwaitingLine | None
    due: DueLine | None


@dataclass(frozen=True, slots=True)
class DeviceView:
    name: str
    since: date


@dataclass(frozen=True, slots=True)
class SummaryView:
    as_of: datetime
    today: date
    send_at: str
    last_run: str
    """Последний вызов расписания за утро «ЧЧ:ММ»: до него экран обещает повтор попыток."""
    sent_at: datetime | None
    awaiting: list[RowView]
    due_today: list[RowView]
    lock_screen: LockScreen
    leader_device: DeviceView | None


@dataclass(frozen=True, slots=True)
class SummarySent:
    """Итог отправки для результата прогона расписания."""

    delivered: bool
    devices: int
    reason: SummaryOutcome


async def send_at(session: AsyncSession) -> str:
    """Время сводки «ЧЧ:ММ» по Ташкенту — порог справочника, его меняет помощник (V24)."""
    return str(await get_setting(session, SettingKey.SUMMARY_AT, DEFAULT_SEND_AT))


def _push_row(row: RowView) -> PushRow:
    """Строка экрана блокировки. Название и подпись укорочены здесь, а не при отправке:
    предпросмотр на вкладке показывает ровно то, что уйдёт, а сводка всегда влезает в
    предел службы уведомлений (`app.domain.push.PUSH_FIELD_LENGTH`)."""
    return PushRow(
        title=None if row.title is None else preview(row.title, PUSH_FIELD_LENGTH),
        section=row.section,
        decision_kind=row.decision_kind,
        context=None if row.context is None else preview(row.context, PUSH_FIELD_LENGTH),
        deviation=row.deviation,
    )


def lock_screen(awaiting: list[RowView], due_today: list[RowView]) -> LockScreen:
    """Экран блокировки: сколько ждёт решения и самое давнее, сколько со сроком и первое."""
    return LockScreen(
        awaiting=AwaitingLine(count=len(awaiting), oldest=_push_row(awaiting[0]))
        if awaiting
        else None,
        due=DueLine(count=len(due_today), first=_push_row(due_today[0])) if due_today else None,
    )


def lock_screen_payload(screen: LockScreen) -> dict[str, Any]:
    """Экран блокировки в том виде, в каком он едет в пуше и в ответе API."""
    return asdict(screen)


async def load(session: AsyncSession, *, now: datetime, zone: ZoneInfo) -> SummaryView:
    """Сводка на момент `now`: списки, экран блокировки, доставка и устройство.

    «Сегодня» считается от того же `now`, что уходит в `as_of`: интерфейс сравнивает с
    ним время отправки, и два разных «сейчас» на одном экране дали бы «ещё не время» у
    уже ушедшей сводки.
    """
    today = local_date(now, zone)
    ladder = await metrics.ladder(session, today=today, zone=zone)
    awaiting_rows = ladder.of(Attention.AWAITING_DECISION)
    due_rows = metrics.due_today(ladder, today)

    # Одна сборка на оба списка: строка со сроком сегодня, ждущая решения, стоит в обоих, и
    # собирать её дважды — два лишних запроса ради той же строки.
    wanted = {(row.section, row.entity_id) for row in (*awaiting_rows, *due_rows)}
    views = await row_views(
        session, [row for row in ladder.rows if (row.section, row.entity_id) in wanted], zone
    )
    by_key = {(view.section, view.entity_id): view for view in views}
    awaiting = [by_key[(row.section, row.entity_id)] for row in awaiting_rows]
    due = [by_key[(row.section, row.entity_id)] for row in due_rows]

    leader = await repo.leader(session)
    sent: datetime | None = None
    device: DeviceView | None = None
    if leader is not None:
        notification = await repo.notification(session, summary_key(today, leader.id))
        sent = notification.sent_at if notification else None
        latest = await repo.latest_subscription(session, leader.id)
        if latest is not None:
            device = DeviceView(name=latest.device, since=local_date(latest.created_at, zone))

    return SummaryView(
        as_of=now,
        today=today,
        send_at=await send_at(session),
        last_run=f"{LAST_SUMMARY_RUN:%H:%M}",
        sent_at=sent,
        awaiting=awaiting,
        due_today=due,
        lock_screen=lock_screen(awaiting, due),
        leader_device=device,
    )


async def blocker(
    session: AsyncSession, push: PushSender, *, now: datetime, zone: ZoneInfo
) -> SummaryOutcome | None:
    """Что мешает отправить сводку сейчас; `None` — пора (`app.domain.push.summary_blocker`).

    Это условие «пора» задачи расписания: пока сводку отправить некому или нечем, день не
    занимается, и следующий вызов расписания пробует снова.
    """
    configured = push.public_key is not None
    leader = await repo.leader(session)
    has_device = (
        leader is not None and await repo.latest_subscription(session, leader.id) is not None
    )
    return summary_blocker(
        local_now=now.astimezone(zone).time(),
        send_at=await send_at(session),
        configured=configured,
        has_device=has_device,
    )


async def send(
    session: AsyncSession, push: PushSender, *, now: datetime, zone: ZoneInfo
) -> SummarySent:
    """Сводка за сегодня — на все устройства руководителя, один раз за день.

    Пуш уходит до фиксации прогона: `run_job` только сбрасывает изменения, а фиксирует
    вызывающий. Сорвётся фиксация после отправки — следующий вызов расписания отправит
    снова, и телефон заменит прежнее уведомление тем же `tag`, а не покажет второе
    (`app.domain.push.summary_payload`).

    Исход — `SummaryOutcome`, а не исключение: и «некому», и «служба не приняла» оставляют
    за собой записанное (уведомление без отметки доставки, отключённые службой подписки), а
    как этот исход отразится на дне, решает задача расписания (`app.jobs.handlers`).
    """
    view = await load(session, now=now, zone=zone)
    leader = await repo.leader(session)
    if leader is None:
        return SummarySent(delivered=False, devices=0, reason=SummaryOutcome.NO_DEVICE)

    payload = summary_payload(view.today, lock_screen_payload(view.lock_screen))
    notification = await notifications.record(
        session,
        user_id=leader.id,
        kind=NotificationKind.MORNING_SUMMARY,
        dedup_key=summary_key(view.today, leader.id),
        payload=payload,
    )
    if notification.sent_at is not None:
        # Повторный прогон руками (`--force`) за уже доставленный день: второй пуш не нужен.
        return SummarySent(delivered=True, devices=0, reason=SummaryOutcome.SENT)
    # Запись прежнего прогона без доставки (служба не приняла, все устройства отключены)
    # получает картину на сейчас, а не ту, что была при том прогоне.
    notification.payload = payload

    if push.public_key is None:
        return SummarySent(delivered=False, devices=0, reason=SummaryOutcome.NOT_CONFIGURED)

    delivery = await notifications.deliver(session, push, notification, now=now)
    if delivery.delivered:
        return SummarySent(delivered=True, devices=delivery.delivered, reason=SummaryOutcome.SENT)
    if delivery.failed:
        return SummarySent(delivered=False, devices=0, reason=SummaryOutcome.REFUSED)
    return SummarySent(delivered=False, devices=0, reason=SummaryOutcome.NO_DEVICE)
