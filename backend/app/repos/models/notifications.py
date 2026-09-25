"""Уведомления (ТЗ 8).

Уведомление — **запись, а не действие**
([ADR-0008](../../../docs/adr/ADR-0008-notifications-escalation.md)). Отправка — отдельный
шаг, читающий эти записи; так недоступность канала не теряет уведомление, а повторный
запуск задачи по расписанию не шлёт второе.

ТЗ 8 называет ровно два повода для пуша — «появилось ждёт вашего решения» и «наступил срок
сегодня» — и требует идемпотентности. Таблица держит именно это: факт уведомления и ключ
повтора. Каналов, расписания, отметок о прочтении здесь нет — их ТЗ не требует.

**Пока таблицу никто не пишет.** Порт отправки (`PushSender`) появится вместе с подпиской
устройства; до него утренняя сводка складывается в результат прогона задачи
(`app.jobs.handlers`), а не сюда.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
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

    # О чём уведомление. Внешним ключом не закрыто: решение, задача, веха и поручение
    # живут в разных таблицах, и `entity_id` указывает то на одну, то на другую.
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Ключ повторной вставки (инвариант о фоновых задачах). Собирается детерминированно из
    # того, что уведомление описывает, — например, объект и дата наступившего срока.
    # Второй прогон той же задачи упирается в уникальность и ничего не отправляет.
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        # «Что нового у меня» — единственный частый запрос, и он всегда по пользователю.
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
    )
