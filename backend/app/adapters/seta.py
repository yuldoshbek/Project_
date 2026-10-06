"""Порт `SetaGateway`: события SETA по поручениям Ижро (ADR-0028, PLAN, блок 3).

Реализация выбирается настройкой `ORBITA_SETA` (`Settings.seta`), и сейчас она одна —
`NoSeta`: SETA не подключена, и событий нет. Это честный ответ, а не ошибка: вклад SETA в
признак жизни поручения пуст, и признак считается по своим источникам, как и без порта.
Подключение — отдельное решение заказчика (docs/PLAN.md, «Вне плана»): тогда появятся
второе значение настройки и вторая реализация, а признак жизни, который спрашивает
`events_since` через `app.services.metrics.seta_life`, не изменится.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol, assert_never

from app.domain.seta import SetaEvent

if TYPE_CHECKING:
    from app.settings import Settings


class SetaGateway(Protocol):
    async def events_since(self, since: datetime) -> list[SetaEvent]:
        """События по поручениям с момента `since` — старые первыми."""
        ...


class NoSeta:
    """SETA не подключена: событий нет."""

    async def events_since(self, since: datetime) -> list[SetaEvent]:
        del since
        return []


def seta_gateway(settings: Settings) -> SetaGateway:
    """Реализация по конфигу. Новое значение `Settings.seta` без ветки здесь не пройдёт mypy."""
    if settings.seta == "none":
        return NoSeta()
    assert_never(settings.seta)
