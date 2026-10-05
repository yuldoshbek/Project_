"""Порт SETA — без подключения (PLAN, блок 3).

1. Без подключения событий нет — пустой список, а не ошибка.
2. Вклад SETA в признак жизни — самое свежее событие по каждому поручению.
3. Видов события ровно четыре, как в ТЗ 11: принято, начато, сдано, продлено.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.adapters.seta import NoSeta, SetaGateway
from app.domain.seta import SetaEvent, SetaEventKind, latest_by_assignment

NOW = datetime(2026, 10, 5, 7, 0, tzinfo=UTC)


async def test_without_connection_there_are_no_events() -> None:
    gateway: SetaGateway = NoSeta()
    assert await gateway.events_since(NOW - timedelta(days=30)) == []


def test_life_sign_takes_the_freshest_event_per_assignment() -> None:
    events = [
        SetaEvent("ПФ-155/3", SetaEventKind.ACCEPTED, NOW - timedelta(days=9)),
        SetaEvent("ПФ-155/3", SetaEventKind.STARTED, NOW - timedelta(days=2)),
        SetaEvent("ПҚ-312/6", SetaEventKind.EXTENDED, NOW - timedelta(days=5)),
        SetaEvent("ПФ-155/3", SetaEventKind.SUBMITTED, NOW - timedelta(days=4)),
    ]
    assert latest_by_assignment(events) == {
        "ПФ-155/3": NOW - timedelta(days=2),
        "ПҚ-312/6": NOW - timedelta(days=5),
    }
    assert latest_by_assignment([]) == {}


def test_four_kinds_as_in_the_spec() -> None:
    assert [kind.value for kind in SetaEventKind] == [
        "accepted",
        "started",
        "submitted",
        "extended",
    ]
