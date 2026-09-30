"""Подписки устройств на уведомления (Web Push, ТЗ 8).

Подписка — то, что браузер выдал в `pushManager.subscribe`: адрес службы уведомлений и
два ключа шифрования. Хранится ровно это, название устройства для строки «Включены на
iPhone руководителя» и отметка, что служба подписку отключила. Подписку создаёт
руководитель на своём телефоне (V28), гасит служба (ответ 404/410 на отправку — строка
остаётся с отметкой `gone_at`) или перевыпуск его ссылки
(`app.services.access.issue_link` — действующие строки удаляются).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey


class PushSubscription(UUIDPrimaryKey, Timestamps, Base):
    """Подписка одного браузера одного пользователя.

    Не журналируется — как и сессия (`app.repos.models.access.Session`): это регистрация
    устройства, а не данные агентства. Браузер обновляет подписку при каждом открытии
    вкладки, и журнал изменений утонул бы в этих записях, не ответив ни на один деловой
    вопрос. Когда уведомления включены, видно по самой таблице — `created_at`.
    """

    __tablename__ = "push_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    endpoint: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    """Адрес службы уведомлений. Уникален: один браузер — одна подписка, и повторная
    подписка того же браузера обновляет строку, а не заводит вторую."""

    # Ключи шифрования содержимого (RFC 8291): открытый ключ браузера и общий секрет.
    p256dh: Mapped[str] = mapped_column(String(100), nullable=False)
    auth: Mapped[str] = mapped_column(String(50), nullable=False)

    device: Mapped[str] = mapped_column(String(50), nullable=False)
    """«iPhone», «Mac», «Android» — по заголовку браузера (`app.domain.push.device_name`)."""

    gone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """Когда служба уведомлений ответила «такой подписки больше нет» (404/410).

    Отметка, а не удаление. Браузер может и дальше отдавать ту же подписку — Chrome не
    сообщает странице, что служба её отозвала, — и вкладка «Сводка» при каждом открытии
    присылала бы её снова: удалённая строка воскресала бы, экран говорил бы «Включены», а
    утром служба снова отвечала бы 410. По отметке сервер отказывает такой подписке (410),
    и браузер заводит новую. Отправка, экран и расписание подписки с отметкой не видят."""

    __table_args__ = (
        # Все подписки получателя — на каждую отправку и на перевыпуск ссылки.
        Index("ix_push_subscriptions_user_id", "user_id"),
    )
