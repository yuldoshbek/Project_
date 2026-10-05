"""API «Доклады и мероприятия» — «готовы ли мы к дате и кто задерживает?» (ТЗ 3.5, 5).

1. **Кто задерживает**: просроченные запросы сведений по источникам, дольше всех — первым.
2. **Ступень подготовки — та же, что на Пульте**: показ — срок, движение — признак жизни.
3. **Пора начинать**: «начать готовить» наступило, а этап — тезисы.
4. **Подготовку ведёт помощник**, по версии; руководитель решает кнопками Пульта.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import demo
from app.domain.clock import local_date, now_utc

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")
BASE = "/api/v1/preparations"
DROUGHT = "Об итогах космического мониторинга засухи"
QUARTER = "Ежеквартальная справка для Администрации Президента"
SATELLITE = "О ходе программы спутниковой группировки"


def today() -> date:
    return local_date(now_utc(), TASHKENT)


@pytest.fixture
async def loaded(session: AsyncSession) -> None:
    now = now_utc()
    await demo.before_visit(session, now=now, zone=TASHKENT)
    await demo.after_visit(session, now=now, zone=TASHKENT)


async def view(api: AsyncClient) -> dict[str, Any]:
    response = await api.get(BASE)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def item(body: dict[str, Any], title: str) -> dict[str, Any]:
    found: dict[str, Any] = next(each for each in body["items"] if each["title"] == title)
    return found


def answer(body: dict[str, Any], key: str) -> dict[str, Any]:
    found: dict[str, Any] = next(each for each in body["questions"] if each["key"] == key)
    return found


@pytest.mark.usefixtures("loaded")
class TestTheSection:
    async def test_who_is_delaying(self, leader_api: AsyncClient) -> None:
        drought = item(await view(leader_api), DROUGHT)

        assert drought["requests"] == {"total": 3, "received": 1, "overdue": 2}
        assert [(each["source"]["name"], each["days"]) for each in drought["delays"]] == [
            ("Министерство экологии", 4),
            (drought["delays"][1]["source"]["name"], 1),
        ]
        assert drought["delays"][0]["source"]["kind"] == "organization"
        assert drought["checklist"] == {"done": 2, "total": 5}

    async def test_steps_and_questions(self, leader_api: AsyncClient) -> None:
        body = await view(leader_api)

        quarter = item(body, QUARTER)
        assert (quarter["step"], quarter["deviation"], quarter["days_left"]) == ("burning", 3, 3)
        readiness = answer(body, "readiness")
        assert readiness["nearest"]["title"] == QUARTER
        assert readiness["nearest"]["missing"] == 0
        assert readiness["count"] == 2
        start_now = answer(body, "start_now")
        assert start_now["rows"] == [item(body, SATELLITE)["id"]]
        # Прошедший показ — в конце и без ступени: готовиться к нему уже нечего.
        assert body["items"][-1]["stage"] == "shown"
        assert body["items"][-1]["step"] is None

    async def test_the_step_is_the_one_the_pult_shows(self, leader_api: AsyncClient) -> None:
        body = await view(leader_api)
        pult = (await leader_api.get("/api/v1/pult")).json()
        on_pult = {r["entity_id"]: r for r in pult["rows"] if r["section"] == "preparations"}
        stepped = {each["id"]: each["step"] for each in body["items"] if each["step"]}

        assert {key: row["step"] for key, row in on_pult.items()} == stepped
        quarter = on_pult[item(body, QUARTER)["id"]]
        assert quarter["target_type"] == "preparation"

    async def test_card(self, leader_api: AsyncClient) -> None:
        drought = item(await view(leader_api), DROUGHT)
        response = await leader_api.get(f"{BASE}/{drought['id']}")
        assert response.status_code == 200, response.text
        card = response.json()

        assert sorted(each["state"] for each in card["info_requests"]) == [
            "overdue",
            "overdue",
            "received",
        ]
        assert len(card["items"]) == 5


@pytest.mark.usefixtures("loaded")
class TestEdits:
    async def test_the_assistant_creates_a_preparation(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        body = {
            "kind": "report",
            "title": "  О готовности наземной станции ",
            "show_on": (today() + timedelta(days=30)).isoformat(),
            "start_on": (today() + timedelta(days=5)).isoformat(),
            "addressee": "president",
        }
        assert (await leader_api.post(BASE, json=body)).status_code == 403
        created = await assistant_api.post(BASE, json=body)
        assert created.status_code == 201, created.text
        added = item(await view(assistant_api), "О готовности наземной станции")
        assert (added["stage"], added["addressee"], added["step"]) == ("theses", "president", None)

        event = body | {"kind": "event"}
        assert (await assistant_api.post(BASE, json=event)).status_code == 422
        late = body | {"start_on": (today() + timedelta(days=40)).isoformat()}
        assert (await assistant_api.post(BASE, json=late)).status_code == 422

    async def test_stage_goes_by_version(self, assistant_api: AsyncClient) -> None:
        target = item(await view(assistant_api), SATELLITE)
        path = f"{BASE}/{target['id']}/stage"

        stale = await assistant_api.put(path, json={"stage": "data", "version": 99})
        assert stale.status_code == 409
        done = await assistant_api.put(path, json={"stage": "data", "version": target["version"]})
        assert done.status_code == 204
        body = await view(assistant_api)
        assert item(body, SATELLITE)["stage"] == "data"
        assert answer(body, "start_now")["rows"] == []

    async def test_received_info_stops_the_delay(self, assistant_api: AsyncClient) -> None:
        drought = item(await view(assistant_api), DROUGHT)
        card = (await assistant_api.get(f"{BASE}/{drought['id']}")).json()
        late = next(each for each in card["info_requests"] if each["state"] == "overdue")

        response = await assistant_api.put(
            f"{BASE}/{drought['id']}/requests/{late['id']}/received",
            json={"received_on": today().isoformat(), "version": late["version"]},
        )
        assert response.status_code == 204
        after = item(await view(assistant_api), DROUGHT)
        assert after["requests"]["overdue"] == 1
        assert len(after["delays"]) == 1

    async def test_checklist_and_new_request(self, assistant_api: AsyncClient) -> None:
        body = await view(assistant_api)
        target = item(body, SATELLITE)
        path = f"{BASE}/{target['id']}"

        created = await assistant_api.post(f"{path}/items", json={"text": "Тезисы"})
        assert created.status_code == 201
        card = (await assistant_api.get(path)).json()
        point = card["items"][0]
        toggled = await assistant_api.put(
            f"{path}/items/{point['id']}", json={"done": True, "version": point["version"]}
        )
        assert toggled.status_code == 204

        person = body["people"][0]
        requested = await assistant_api.post(
            f"{path}/requests",
            json={
                "what": "Данные о спутниках",
                "source_kind": "person",
                "source_id": person["id"],
                "due_on": (today() - timedelta(days=2)).isoformat(),
            },
        )
        assert requested.status_code == 201, requested.text
        after = item(await view(assistant_api), SATELLITE)
        assert after["checklist"] == {"done": 1, "total": 1}
        assert after["delays"][0]["source"] == {
            "kind": "person",
            "id": person["id"],
            "name": person["name"],
        }

    async def test_a_question_on_a_preparation(
        self, assistant_api: AsyncClient, leader_api: AsyncClient
    ) -> None:
        target = item(await view(assistant_api), DROUGHT)
        asked = await assistant_api.post(
            "/api/v1/questions",
            json={"target_type": "preparation", "target_id": target["id"], "text": "Переносим?"},
        )
        assert asked.status_code == 201, asked.text
        assert item(await view(leader_api), DROUGHT)["step"] == "awaiting_decision"
