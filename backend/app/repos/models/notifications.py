"""Уведомления (ТЗ 8).

Уведомление — **запись, а не действие**
([ADR-0036](../../../docs/adr/ADR-0036-web-push.md)). Запись делается в одной транзакции с
событием, отправка — отдельным шагом (`app.services.notifications.deliver`); так повторный
запуск задачи по расписанию упирается в ключ повтора и второго пуша не шлёт.

ТЗ 8 называет ровно два повода для пуша — «появилось ждёт вашего решения» и утренняя
сводка со сроками сегодня — и требует идемпотентности. Таблица держит именно это: факт
уведомления, ключ повтора, содержимое пуша и отметку доставки. Каналов, расписания,
отметок о прочтении здесь нет — их ТЗ не требует.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey


class Notification(UUIDPrimaryKey, Timestamps, Base):
    """Повод сказать пользователю, что что-то произошло."""

    __tablename__ = "notifications"

    # Кому показать. Сотрудник здесь стоять не может: сотрудники — не пользователи
    # системы, и показать им внутри неё нечего (ADR-0011).
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    kind: Mapped[str] = mapped_column(String(50), nullable=False)

    # О чём уведомление. Внешним ключом не закрыто: вопрос, решение, задача и поручение
    # живут в разных таблицах, и `entity_id` указывает то на одну, то на другую. У сводки
    # записи нет вовсе — она о дне целиком, поэтому оба поля необязательны.
    entity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Ключ повторной вставки (инвариант 10). Собирается детерминированно из того, что
    # уведомление описывает: день и получатель сводки, вопрос (`app.domain.push`). Второй
    # прогон той же задачи упирается в уникальность и получает прежнюю запись: доставленную
    # (`sent_at`) второй раз не отправляет, недоставленную — пробует доставить снова.
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

    # Содержимое пуша — данные, а не текст: фразу собирает сервис-воркер (ADR-0036).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """Когда пуш принят службой уведомлений хотя бы для одного устройства. Пусто — не
    доставлен: устройства нет, служба не ответила или уведомления не настроены."""

    __table_args__ = (
        # «Что нового у меня» — единственный частый запрос, и он всегда по пользователю.
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
    )
