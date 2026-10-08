"""Порт SETA — без подключения (PLAN, блок 3).

1. Порт выбирается настройкой; без подключения событий нет — пустой список, а не ошибка,
   и вклад SETA в признак жизни пуст.
2. Вклад SETA в признак жизни — самое свежее событие по каждому поручению.
3. Видов события ровно четыре, как в ТЗ 10: принято, начато, сдано, продлено.
4. Событие SETA свежее своих — признак жизни поручения, и в разделе «Ижро», и на Пульте:
   подключение добавляет событие, а не меняет расчёт (ТЗ 10).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import demo
from app.adapters.seta import NoSeta, SetaGateway, seta_gateway
from app.domain.clock import local_date, now_utc
from app.domain.ijro import LifeSource
from app.domain.ijro_control import LifeSign, sign_of_life
from app.domain.seta import SetaEvent, SetaEventKind, assignment_key, latest_by_assignment
from app.repos.models import IjroAssignment, IjroDocument
from app.services import metrics
from app.settings import Settings

NOW = datetime(2026, 10, 5, 7, 0, tzinfo=UTC)
TASHKENT = ZoneInfo("Asia/Tashkent")
IJRO = "/api/v1/ijro"


async def test_without_connection_there_are_no_events(settings: Settings) -> None:
    assert settings.seta == "none"
    gateway: SetaGateway = seta_gateway(settings)
    assert isinstance(gateway, NoSeta)
    assert await gateway.events_since(NOW - timedelta(days=30)) == []
    assert await metrics.seta_life(zone=TASHKENT) == {}


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


def test_on_the_same_day_the_sign_names_our_own_event() -> None:
    """Отметка и событие SETA в один день — подпись «отметка»: своё названо раньше."""
    day = date(2026, 10, 1)
    sign = sign_of_life([LifeSign(day, LifeSource.CONTROL_MARK), LifeSign(day, LifeSource.SETA)])
    assert sign == LifeSign(day, LifeSource.CONTROL_MARK)


class FakeSeta:
    """Подключённая SETA, которая отдаёт заданные события."""

    def __init__(self, events: list[SetaEvent]) -> None:
        self.events = events

    async def events_since(self, since: datetime) -> list[SetaEvent]:
        return [each for each in self.events if each.at >= since]


def row(view: dict[str, Any], code: str, band: str) -> dict[str, Any]:
    found: list[dict[str, Any]] = [
        item for item in view["items"] if item["document"]["code"] == code and item["band"] == band
    ]
    assert len(found) == 1, (code, band)
    return found[0]


async def on_pult(api: AsyncClient) -> set[str]:
    rows = (await api.get("/api/v1/pult")).json()["rows"]
    return {each["entity_id"] for each in rows}


@pytest.mark.infra
async def test_a_fresher_seta_event_is_the_sign_of_life(
    session: AsyncSession, leader_api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = now_utc()
    await demo.before_visit(session, now=now, zone=TASHKENT)
    await demo.after_visit(session, now=now, zone=TASHKENT)
    quiet = row((await leader_api.get(IJRO)).json(), "ПФ-155", "9-банд")
    assert quiet["step"] == "silent"
    assert quiet["id"] in await on_pult(leader_api)
    # SETA называет поручение номером из таблицы Ижро, а не кодом записи ORBITA.
    found = (
        await session.execute(
            select(IjroDocument.code_norm, IjroAssignment.band, IjroAssignment.code)
            .join(IjroDocument, IjroDocument.id == IjroAssignment.document_id)
            .where(IjroAssignment.id == uuid.UUID(quiet["id"]))
        )
    ).one()
    code = assignment_key(found.code_norm, found.band)

    seta = FakeSeta(
        [
            SetaEvent(code, SetaEventKind.ACCEPTED, now - timedelta(days=40)),
            SetaEvent(code, SetaEventKind.STARTED, now),
            SetaEvent("нет-такого-поручения", SetaEventKind.SUBMITTED, now),
            # Код записи ORBITA — не номер SETA: такое событие не должно совпасть.
            SetaEvent(found.code, SetaEventKind.SUBMITTED, now + timedelta(days=1)),
        ]
    )
    monkeypatch.setattr(metrics, "seta_gateway", lambda _settings: seta)

    after = row((await leader_api.get(IJRO)).json(), "ПФ-155", "9-банд")
    today = local_date(now, TASHKENT).isoformat()
    assert after["sign_of_life"] == {"on": today, "source": "seta"}
    assert after["step"] is None
    # Пульт берёт тот же признак жизни: поручение перестало молчать в обоих местах.
    assert quiet["id"] not in await on_pult(leader_api)


def test_assignment_key_is_the_table_number() -> None:
    assert assignment_key("ПФ-155", "9-банд") == "ПФ-155/9-банд"
    # Строка без пункта — законное состояние таблицы: номер — сам документ.
    assert assignment_key("ПҚ-312", None) == "ПҚ-312"
