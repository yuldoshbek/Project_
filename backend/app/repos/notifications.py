"""Запросы уведомлений: получатель, его подписки, запись уведомления по ключу повтора.

Получатель один — руководитель (V28), и ищется он по роли, а не хранится настройкой:
роль у пользователя уникальна (`app.repos.models.people.User`).

Подписка, которую служба уведомлений отключила (`gone_at`), остаётся в таблице отметкой,
но ни один запрос здесь её как подписку не отдаёт: ни отправке, ни экрану, ни расписанию
(почему отметка, а не удаление, — в модели `app.repos.models.push`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.people import Role
from app.repos.models import Notification, PushSubscription, User


async def leader(session: AsyncSession) -> User | None:
    found: User | None = await session.scalar(
        select(User).where(User.role == Role.LEADER.value, User.is_active)
    )
    return found


async def subscriptions(session: AsyncSession, user_id: uuid.UUID) -> list[PushSubscription]:
    """Действующие подписки пользователя — старые первыми, порядок отправки предсказуем."""
    rows = await session.scalars(
        select(PushSubscription)
        .where(PushSubscription.user_id == user_id, PushSubscription.gone_at.is_(None))
        .order_by(PushSubscription.created_at, PushSubscription.id)
    )
    return list(rows)


async def latest_subscription(session: AsyncSession, user_id: uuid.UUID) -> PushSubscription | None:
    """Последнее включённое устройство — его экран называет «iPhone руководителя, с 21.09»."""
    found: PushSubscription | None = await session.scalar(
        select(PushSubscription)
        .where(PushSubscription.user_id == user_id, PushSubscription.gone_at.is_(None))
        .order_by(PushSubscription.created_at.desc(), PushSubscription.id.desc())
        .limit(1)
    )
    return found


async def upsert_subscription(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    endpoint: str,
    p256dh: str,
    auth: str,
    device: str,
) -> datetime | None:
    """Подписка по адресу: новая — вставкой, известная — обновлением ключей.

    Одним запросом `ON CONFLICT`, а не «прочитать и решить»: интерфейс сверяет подписку при
    каждом открытии вкладки, и две вкладки одного телефона приходят одновременно — вторая
    упала бы на уникальности адреса. Момент создания не трогается: «включены с 21.09»
    остаётся датой, когда руководитель включил уведомления, а не последним открытием.

    Адрес, который служба уже отключила (`gone_at`), не обновляется и не воскресает:
    запрос ничего не возвращает, и это `None`.
    """
    statement = (
        insert(PushSubscription)
        .values(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth, device=device)
        .on_conflict_do_update(
            index_elements=[PushSubscription.endpoint],
            set_={
                "user_id": user_id,
                "p256dh": p256dh,
                "auth": auth,
                "device": device,
                # Правило `onupdate` модели на ON CONFLICT не срабатывает — только явно.
                "updated_at": func.now(),
            },
            where=PushSubscription.gone_at.is_(None),
        )
        .returning(PushSubscription.created_at)
    )
    created_at: datetime | None = (await session.execute(statement)).scalar_one_or_none()
    return created_at


async def notification(session: AsyncSession, dedup_key: str) -> Notification | None:
    found: Notification | None = await session.scalar(
        select(Notification).where(Notification.dedup_key == dedup_key)
    )
    return found


async def add_notification(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    kind: str,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
    dedup_key: str,
    payload: dict[str, Any],
) -> Notification:
    """Уведомление по ключу повтора: есть — возвращается прежнее, нет — заводится.

    `ON CONFLICT DO NOTHING`, а не исключение уникальности: исключение откатило бы всю
    транзакцию — вместе с вопросом, ради которого уведомление и заводится.
    """
    await session.execute(
        insert(Notification)
        .values(
            user_id=user_id,
            kind=kind,
            entity_type=entity_type,
            entity_id=entity_id,
            dedup_key=dedup_key,
            payload=payload,
        )
        .on_conflict_do_nothing(index_elements=[Notification.dedup_key])
    )
    found = await notification(session, dedup_key)
    assert found is not None, "уведомление только что вставлено или уже было"
    return found


async def delete_unsent(session: AsyncSession, dedup_key: str) -> None:
    """Убирает уведомление, которое так и не ушло. Ушедшее остаётся — как след отправки."""
    await session.execute(
        delete(Notification).where(
            Notification.dedup_key == dedup_key, Notification.sent_at.is_(None)
        )
    )
