"""Уведомления.

Уведомление — **запись, а не действие** ([ADR-0008](../../../docs/adr/ADR-0008-notifications.md)).
Отправка — отдельный шаг, читающий эти записи; так недоступность почты или Telegram не
теряет уведомление, а перезапуск задания не порождает второе.

Здесь заведена только та часть таблицы, которая нужна упоминаниям в комментариях
(ORB-016). Каналы, расписание, отметка о прочтении и отправке появятся вместе с центром
уведомлений (ORB-037) и рассылкой (ORB-035, ORB-040) — своими миграциями. Заводить их
сейчас значило бы положить в схему шесть полей, которые полгода будут пустыми, и потом
гадать, что каждое из них должно было значить.
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

    # Кому показать. Упомянутый сотрудник здесь стоять не может: сотрудники — не
    # пользователи системы, и показать им внутри неё нечего (Q24, ADR-0011).
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    kind: Mapped[str] = mapped_column(String(50), nullable=False)

    # О чём уведомление. Внешним ключом не закрыто по той же причине, что у комментариев:
    # `entity_id` указывает то на одну таблицу, то на другую.
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Ключ повторной вставки (инвариант 6 из CLAUDE.md). Собирается детерминированно из
    # того, что уведомление описывает: правка комментария, повторяющая то же упоминание,
    # упирается в уникальность и ничего не делает. Без него человек получал бы новое
    # сообщение каждый раз, когда автор поправил в реплике запятую.
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        # «Что нового у меня» — единственный частый запрос, и он всегда по пользователю.
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
    )
