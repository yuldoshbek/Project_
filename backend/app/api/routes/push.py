"""Подписка устройства руководителя на утреннюю сводку и пуши (ТЗ 8, V28).

Один путь под одну кнопку экрана — «Включить уведомления» на вкладке «Сводка»; её же
интерфейс зовёт при каждом открытии вкладки, когда у браузера подписка уже есть. Пути
отписки нет: на экране нет кнопки, которая бы его звала. Подписка гаснет, когда служба
уведомлений отвечает «такой больше нет» (строка остаётся с отметкой, и тот же адрес больше
не принимается), или при перевыпуске ссылки (`app.services.access.issue_link`).
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from fastapi import Request
from pydantic import BaseModel

from app.api.deps import SessionDep, SettingsDep
from app.api.security import CurrentUser
from app.api.transaction import transactional_router
from app.domain.clock import local_date
from app.services import notifications as service

router = transactional_router(tags=["уведомления"])


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionRequest(BaseModel):
    """`PushSubscription.toJSON()` как есть. Лишние поля (`expirationTime`) не читаются."""

    endpoint: str
    keys: SubscriptionKeys


class SubscriptionResponse(BaseModel):
    since: date
    device: str


@router.put(
    "/push/subscription",
    response_model=SubscriptionResponse,
    summary="Уведомления на устройстве руководителя: включить или сверить",
)
async def put_subscription(
    body: SubscriptionRequest,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> SubscriptionResponse:
    """Подписка по адресу: повтор с тем же адресом обновляет ключи и не сдвигает «с какого
    дня» включено. Помощник получает отказ — уведомления идут руководителю (V28). Адрес,
    который служба уведомлений уже отключила, получает 410: браузер отписывается и по
    кнопке заводит новый."""
    subscribed = await service.subscribe(
        session,
        user=user,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=request.headers.get("user-agent"),
    )
    return SubscriptionResponse(
        since=local_date(subscribed.created_at, ZoneInfo(settings.timezone)),
        device=subscribed.device,
    )
