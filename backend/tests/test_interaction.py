"""API «Взаимодействие» — обещания экрана, утверждённого заказчиком 01.10.2026.

1. **Четыре вопроса** в порядке экрана, у каждого — те же строки, что считались.
2. **Скорость ответа — медиана, только при пяти ответах и больше** (ТЗ 4, критерий 4).
3. **Ступень письма и соглашения та же, что на Пульте** (инвариант 2): входящее горит и
   просрочивается, наше исходящее ждёт чужих (V39), соглашение спит после 90 дней.
4. **Роль подписывает действие**: письмо и ответ — помощник, оценка — руководитель (V38),
   шаг соглашения — помощник; правки — по версии (инвариант 15).
5. **Решение и вопрос по письму** — теми же кнопками, что на Пульте.
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
from app.domain.interaction import Question

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")
BASE = "/api/v1/interaction"


def today() -> date:
    return local_date(now_utc(), TASHKENT)


@pytest.fixture
async def loaded(session: AsyncSession) -> None:
    now = now_utc()
    await demo.before_visit(session, now=now, zone=TASHKENT)
    await demo.after_visit(session, now=now, zone=TASHKENT)


async def section(api: AsyncClient) -> dict[str, Any]:
    response = await api.get(BASE)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def letter(view: dict[str, Any], subject: str) -> dict[str, Any]:
    found: list[dict[str, Any]] = [each for each in view["letters"] if each["subject"] == subject]
    assert len(found) == 1, subject
    return found[0]


def agreement(view: dict[str, Any], title: str) -> dict[str, Any]:
    found: dict[str, Any] = next(each for each in view["agreements"] if each["title"] == title)
    return found


def answer(view: dict[str, Any], key: Question) -> dict[str, Any]:
    found: dict[str, Any] = next(each for each in view["questions"] if each["key"] == key.value)
    return found


def organization(view: dict[str, Any], short: str) -> dict[str, Any]:
    found: dict[str, Any] = next(
        each for each in view["organizations"] if (each["short_name"] or each["name"]) == short
    )
    return found


TRANS_6 = "О согласовании «дорожной карты» навигационных услуг"


@pytest.mark.usefixtures("loaded")
class TestTheSection:
    async def test_four_answers_in_the_screen_order(self, leader_api: AsyncClient) -> None:
        view = await section(leader_api)

        assert [each["key"] for each in view["questions"]] == [key.value for key in Question]
        waiting = answer(view, Question.NOT_ANSWERING)
        assert (waiting["count"], len(waiting["organizations"])) == (5, 4)
        assert sum(group["count"] for group in waiting["organizations"]) == waiting["count"]
        known = {each["id"] for each in view["letters"]}
        assert set(waiting["rows"]) <= known
        assert len(view["letters"]) == 24
        assert len(view["agreements"]) == 6

    async def test_speed_is_a_median_from_five_replies(self, leader_api: AsyncClient) -> None:
        view = await section(leader_api)
        speed = answer(view, Question.SPEED)

        assert [
            (each["organization"]["short_name"], each["median_days"]) for each in speed["measured"]
        ] == [
            ("Минтранс", 25),
            (None, 10),
        ]
        assert speed["little_data"] == 3
        assert organization(view, "Минцифры")["speed"] == {"letters": 1, "median_days": None}
        assert organization(view, "Министерство экологии")["ratings"] == {
            "substance": 3,
            "formal": 1,
            "off_topic": 0,
        }

    async def test_steps_of_letters_and_agreements(self, leader_api: AsyncClient) -> None:
        view = await section(leader_api)

        assert (letter(view, TRANS_6)["step"], letter(view, TRANS_6)["deviation"]) == (
            "blocked_by_others",
            19,
        )
        samarkand = letter(view, "О выделении участка под наземную станцию")
        assert (samarkand["step"], samarkand["deviation"]) == ("blocked_by_others", 38)
        assert letter(view, "О данных о трафике для модели загруженности")["step"] is None
        digital = letter(view, "О подключении к единому реестру космической деятельности")
        assert (digital["step"], digital["deviation"]) == ("overdue", 2)
        station = letter(view, "Отчёт о загрузке наземной станции за квартал")
        assert (station["step"], station["deviation"]) == ("burning", 2)
        assert station["link"]["type"] == "project"
        assert letter(view, TRANS_6)["link"] == {
            "type": "ijro",
            "id": letter(view, TRANS_6)["link"]["id"],
            "title": "ВМҚ-512 · 8-банд",
        }

        sleeping = answer(view, Question.SLEEPING)
        titles = {each["id"]: each["title"] for each in view["agreements"]}
        assert {titles[each] for each in sleeping["rows"]} == {
            "Меморандум о навигационных услугах",
            "Memorandum on Space Applications cooperation",
        }
        telecom = agreement(view, "Договор на каналы связи наземной станции")
        assert (telecom["step"], telecom["deviation"], telecom["sleeping"]) == ("overdue", 5, False)
        assert organization(view, "Узбектелеком")["overdue_steps"] == 1

    async def test_the_step_is_the_one_the_pult_shows(self, leader_api: AsyncClient) -> None:
        view = await section(leader_api)
        pult = (await leader_api.get("/api/v1/pult")).json()
        on_pult = {
            r["entity_id"]: r["step"]
            for r in pult["rows"]
            if r["section"] in {"letters", "agreements"}
        }
        stepped = {
            each["id"]: each["step"]
            for each in [*view["letters"], *view["agreements"]]
            if each["step"]
        }
        assert on_pult == stepped
        row = next(r for r in pult["rows"] if r["entity_id"] == letter(view, TRANS_6)["id"])
        assert (row["context"], row["target_type"]) == ("Минтранс", "letter")

    async def test_organization_card(self, leader_api: AsyncClient) -> None:
        view = await section(leader_api)
        eco = organization(view, "Министерство экологии")
        response = await leader_api.get(f"{BASE}/organizations/{eco['id']}")
        assert response.status_code == 200, response.text
        card = response.json()

        assert len(card["letters"]) == 8
        assert [each["title"] for each in card["agreements"]] == [
            "Меморандум о мониторинге водных ресурсов"
        ]
        assert {each["place"] for each in card["ijro"]} == {"ПҚ-312 · 2-банд", "ПҚ-312 · 11-банд"}
        assert card["phone"] == "+998 71 207-00-00"
        assert all(each["role"] for each in card["projects"])


@pytest.mark.usefixtures("loaded")
class TestEdits:
    async def test_the_assistant_marks_a_reply_by_version(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        target = letter(await section(assistant_api), TRANS_6)
        path = f"{BASE}/letters/{target['id']}/answer"
        body = {"on": today().isoformat(), "number": "11-1020", "version": target["version"]}

        assert (await leader_api.put(path, json=body)).status_code == 403
        stale = await assistant_api.put(path, json=body | {"version": target["version"] + 1})
        assert stale.status_code == 409
        early = await assistant_api.put(
            path, json=body | {"on": (today() - timedelta(days=60)).isoformat()}
        )
        assert early.status_code == 422
        assert (await assistant_api.put(path, json=body)).status_code == 204

        view = await section(assistant_api)
        done = letter(view, TRANS_6)
        assert (done["state"], done["step"], done["reply"]["number"]) == (
            "answered",
            None,
            "11-1020",
        )
        assert done["id"] not in answer(view, Question.NOT_ANSWERING)["rows"]

    async def test_the_leader_rates_a_received_reply(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        view = await section(leader_api)
        target = letter(view, "О совместной рабочей группе по мониторингу")
        path = f"{BASE}/letters/{target['id']}/rating"

        assert (
            await assistant_api.put(path, json={"rating": "formal", "version": target["version"]})
        ).status_code == 403
        rated = await leader_api.put(path, json={"rating": "formal", "version": target["version"]})
        assert rated.status_code == 204
        assert letter(await section(leader_api), target["subject"])["rating"] == "formal"
        cleared = await leader_api.put(
            path, json={"rating": None, "version": target["version"] + 1}
        )
        assert cleared.status_code == 204

        incoming = letter(view, "Запрос космических снимков пастбищ Каракалпакстана")
        refused = await leader_api.put(
            f"{BASE}/letters/{incoming['id']}/rating",
            json={"rating": "formal", "version": incoming["version"]},
        )
        assert refused.status_code == 422

    async def test_the_assistant_adds_a_letter(self, assistant_api: AsyncClient) -> None:
        view = await section(assistant_api)
        org = organization(view, "Минвуз")
        body = {
            "direction": "outgoing",
            "organization_id": org["id"],
            "subject": "  О данных для отчёта  по засухе ",
            "sent_on": today().isoformat(),
            "due_on": (today() + timedelta(days=10)).isoformat(),
        }

        created = await assistant_api.post(f"{BASE}/letters", json=body)
        assert created.status_code == 201, created.text
        added = letter(await section(assistant_api), "О данных для отчёта по засухе")
        assert (added["state"], added["step"], added["days"]) == ("waiting_reply", None, 0)

        late = body | {"due_on": (today() - timedelta(days=1)).isoformat()}
        assert (await assistant_api.post(f"{BASE}/letters", json=late)).status_code == 422
        assert (
            await assistant_api.post(f"{BASE}/letters", json=body | {"subject": "   "})
        ).status_code == 422

    async def test_a_next_step_wakes_a_sleeping_agreement(self, assistant_api: AsyncClient) -> None:
        target = agreement(await section(assistant_api), "Меморандум о навигационных услугах")
        assert target["sleeping"]

        response = await assistant_api.put(
            f"{BASE}/agreements/{target['id']}/next-step",
            json={"next_step": "Созвониться с Минтрансом", "next_step_on": None, "version": 1},
        )
        assert response.status_code == 204
        after = agreement(await section(assistant_api), "Меморандум о навигационных услугах")
        assert (after["sleeping"], after["quiet_days"], after["step"]) == (False, 0, None)

    async def test_a_question_on_a_letter_awaits_the_leader(
        self, assistant_api: AsyncClient, leader_api: AsyncClient
    ) -> None:
        target = letter(await section(assistant_api), TRANS_6)
        asked = await assistant_api.post(
            "/api/v1/questions",
            json={"target_type": "letter", "target_id": target["id"], "text": "Звонить министру?"},
        )
        assert asked.status_code == 201, asked.text
        assert letter(await section(leader_api), TRANS_6)["step"] == "awaiting_decision"

        decided = await leader_api.post(
            "/api/v1/decisions",
            json={"target_type": "letter", "target_id": target["id"], "kind": "escalate"},
        )
        assert decided.status_code == 201, decided.text

    async def test_new_thresholds_are_in_management(self, leader_api: AsyncClient) -> None:
        body = (await leader_api.get("/api/v1/management")).json()
        by_key = {each["key"]: each for each in body["thresholds"]}
        assert (by_key["sleeping_days"]["value"], by_key["sleeping_days"]["affected"]) == (90, 2)
        assert by_key["min_letters_for_speed"]["affected"] == 2
