"""Порт `SetaGateway`: события SETA по поручениям Ижро (ADR-0028, PLAN, блок 3).

Реализация сейчас одна — `NoSeta`: SETA не подключена, и событий нет. Это честный ответ, а
не ошибка: признак жизни поручения считается по своим трём источникам, как и без порта.
Подключение — отдельное решение заказчика (docs/PLAN.md, «Вне плана»): тогда появится
вторая реализация, а сервисы, которые спрашивают `events_since`, не изменятся.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.seta import SetaEvent


class SetaGateway(Protocol):
    async def events_since(self, since: datetime) -> list[SetaEvent]:
        """События по поручениям с момента `since` — старые первыми."""
        ...


class NoSeta:
    """SETA не подключена: событий нет."""

    async def events_since(self, since: datetime) -> list[SetaEvent]:
        del since
        return []
