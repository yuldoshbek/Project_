"""Действия обхода — для «сделано на неделе» (ТЗ 7, допущение V20).

Сама очередь обхода не хранится: она считается из данных, и пункт уходит, когда данные
поправлены. Хранится только то, что сделано из обхода, — одна строка на действие, в той же
транзакции, что и правка записи (инвариант 5). Журнал изменений на этот вопрос не отвечает:
он знает, что задачу закрыли, но не знает, что закрыли её из обхода.

В строке — только момент: экран показывает число сделанного с понедельника, а что и кем
поправлено, уже записано в журнал самой правкой. Остальное было бы полем «на будущее»
(инвариант 14).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, UUIDPrimaryKey


class RoundMark(UUIDPrimaryKey, Base):
    """Одно действие обхода. Без `Timestamps`, как `AuditLog`: строка не меняется."""

    __tablename__ = "round_actions"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # «Сделано на неделе» — действия с понедельника.
        Index("ix_round_actions_created_at", "created_at"),
    )
