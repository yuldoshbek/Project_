"""Уведомления руководителю: подписка устройства, запись повода, доставка (ТЗ 8, ADR-0036).

Запись и доставка — два шага, и между ними граница транзакции. Запись делается вместе с
событием (вопросом, сводкой), доставка — после: пуш о вопросе уходит, когда вопрос уже
зафиксирован (`app.api.transaction.after_commit`), иначе телефон узнал бы о вопросе,
которого из-за отката так и не было.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.push import PushOutcome, PushSender, PushTarget
from app.domain.errors import GoneError
from app.domain.people import Role
from app.domain.push import (
    NotificationKind,
    check_subscriber,
    clean_subscription,
    device_name,
)
from app.repos import notifications as repo
from app.repos.models import Notification, User


@dataclass(frozen=True, slots=True)
class Subscribed:
    """Что ответить экрану: с какого момента и на каком устройстве включено."""

    created_at: datetime
    device: str


@dataclass(frozen=True, slots=True)
class Delivery:
    """Итог доставки одного уведомления по всем устройствам получателя."""

    delivered: int = 0
    gone: int = 0
    failed: int = 0


async def subscribe(
    session: AsyncSession,
    *,
    user: User,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
) -> Subscribed:
    """Подписка устройства руководителя — новая или сверка уже известной.

    Интерфейс зовёт это и после «Включить», и при каждом открытии вкладки, когда у
    браузера подписка уже есть: после смены ключа сервера или перевыпуска ссылки сервер
    узнаёт о ней снова без участия руководителя.

    Подписку, которую служба уже отключила, браузер может присылать и дальше — ему об этом
    не сообщают. Ответ «больше не действует» говорит интерфейсу отписать браузер: тогда
    появляется «Включить уведомления», и новая подписка получает новый адрес.
    """
    check_subscriber(Role(user.role))
    subscription = clean_subscription(endpoint=endpoint, p256dh=p256dh, auth=auth)
    device = device_name(user_agent)
    created_at = await repo.upsert_subscription(
        session,
        user_id=user.id,
        endpoint=subscription.endpoint,
        p256dh=subscription.p256dh,
        auth=subscription.auth,
        device=device,
    )
    if created_at is None:
        raise GoneError(
            "Эта подписка больше не действует: служба уведомлений её отключила. "
            "Включите уведомления заново"
        )
    return Subscribed(created_at=created_at, device=device)


async def record(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    kind: NotificationKind,
    dedup_key: str,
    payload: dict[str, Any],
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> Notification:
    """Повод уведомления. Второй с тем же ключом не заводится — возвращается первый."""
    return await repo.add_notification(
        session,
        user_id=user_id,
        kind=kind.value,
        entity_type=entity_type,
        entity_id=entity_id,
        dedup_key=dedup_key,
        payload=payload,
    )


async def deliver(
    session: AsyncSession, push: PushSender, notification: Notification, *, now: datetime
) -> Delivery:
    """Отправляет уведомление на все устройства получателя.

    Уже доставленное второй раз не отправляется (инвариант 10). Подписку, которой больше
    нет, служба называет ответом 404/410 — она получает отметку `gone_at` здесь же, иначе
    каждое утро сводка стучалась бы в пустоту и выглядела бы недоставленной. Отметка, а не
    удаление, — почему, сказано в модели `app.repos.models.push`.
    """
    if notification.sent_at is not None:
        return Delivery()

    kind = NotificationKind(notification.kind)
    outcomes: dict[PushOutcome, int] = dict.fromkeys(PushOutcome, 0)
    for subscription in await repo.subscriptions(session, notification.user_id):
        outcome = await push.send(
            PushTarget(
                endpoint=subscription.endpoint,
                p256dh=subscription.p256dh,
                auth=subscription.auth,
            ),
            notification.payload,
            ttl=kind.ttl,
            urgency=kind.urgency,
        )
        outcomes[outcome] += 1
        if outcome is PushOutcome.GONE:
            subscription.gone_at = now

    if outcomes[PushOutcome.DELIVERED]:
        notification.sent_at = now
    await session.flush()
    return Delivery(
        delivered=outcomes[PushOutcome.DELIVERED],
        gone=outcomes[PushOutcome.GONE],
        failed=outcomes[PushOutcome.FAILED],
    )


async def deliver_pending(
    session: AsyncSession, push: PushSender, *, dedup_key: str, now: datetime
) -> Delivery:
    """Доставка записанного уведомления по ключу — для отправки после фиксации.

    Повтора для пуша о вопросе нет, и он не нужен: вопрос, который всё ещё ждёт, будет в
    следующей утренней сводке (ADR-0036).
    """
    found = await repo.notification(session, dedup_key)
    if found is None:
        return Delivery()
    return await deliver(session, push, found, now=now)


async def withdraw(session: AsyncSession, *, dedup_key: str) -> None:
    """Отменённый повод: неотправленное уведомление удаляется, ушедшее остаётся."""
    await repo.delete_unsent(session, dedup_key)
