"""API «Ижро» — обещания экрана, утверждённого заказчиком 30.09.2026.

1. **Двенадцать вопросов** (V31) в порядке экрана, у каждого — те же строки, что считались.
2. **Ступень строки та же, что на Пульте** (инвариант 2): поручение горит в обоих местах
   или ни в одном.
3. **Срок «месяцем» и «до конца года» не горит** (V33); сданное и снятое ступени не имеют
   (V32).
4. **Контрольная отметка — оба** и сразу признак жизни (ТЗ 4, V35); этап, проблема,
   «запрошено продление», сопоставление ФИО и задача — помощник, по версии (инвариант 15).
5. **Решение и вопрос по поручению** — теми же кнопками, что на Пульте.
6. **«Разложить на задачу»** — за три рабочих дня до срока, со связью (V34, ADR-0033).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import demo
from app.domain.clock import local_date, now_utc
from app.domain.ijro_control import Question, workdays_before
from app.repos.models import IjroPersonAlias, Task

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")
IJRO = "/api/v1/ijro"


def today() -> date:
    return local_date(now_utc(), TASHKENT)


@pytest.fixture
async def loaded(session: AsyncSession) -> None:
    now = now_utc()
    await demo.before_visit(session, now=now, zone=TASHKENT)
    await demo.after_visit(session, now=now, zone=TASHKENT)


async def section(api: AsyncClient) -> dict[str, Any]:
    response = await api.get(IJRO)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def row(view: dict[str, Any], code: str, band: str) -> dict[str, Any]:
    found: list[dict[str, Any]] = [
        item for item in view["items"] if item["document"]["code"] == code and item["band"] == band
    ]
    assert len(found) == 1, (code, band)
    return found[0]


def answer(view: dict[str, Any], key: Question) -> dict[str, Any]:
    found: dict[str, Any] = next(each for each in view["questions"] if each["key"] == key.value)
    return found


async def card(api: AsyncClient, assignment_id: str) -> dict[str, Any]:
    response = await api.get(f"{IJRO}/assignments/{assignment_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


@pytest.mark.usefixtures("loaded")
class TestTheSection:
    async def test_twelve_answers_in_the_screen_order(self, leader_api: AsyncClient) -> None:
        view = await section(leader_api)

        assert [each["key"] for each in view["questions"]] == [key.value for key in Question]
        assert len(view["items"]) == 29
        assert len(view["documents"]) == 4
        assert view["batches"][0]["file"] == "АП топшириқлари 3-чорак.docx"
        assert view["table_on"] == (today() - timedelta(days=3)).isoformat()
        known = {item["id"] for item in view["items"]}
        for each in view["questions"]:
            assert set(each["rows"]) <= known, each["key"]

    async def test_burning_answer_counts_the_rows_it_lists(self, leader_api: AsyncClient) -> None:
        view = await section(leader_api)
        burning = answer(view, Question.BURNING)
        steps = {item["id"]: item["step"] for item in view["items"]}

        assert burning["overdue"] == sum(steps[i] == "overdue" for i in burning["rows"])
        assert burning["burning"] + burning["overdue"] == len(burning["rows"])
        assert {steps[i] for i in burning["rows"]} <= {"overdue", "burning"}

    async def test_the_step_is_the_one_the_pult_shows(self, leader_api: AsyncClient) -> None:
        view = await section(leader_api)
        pult = (await leader_api.get("/api/v1/pult")).json()
        on_pult = {r["entity_id"]: r["step"] for r in pult["rows"] if r["section"] == "ijro"}

        stepped = {item["id"]: item["step"] for item in view["items"] if item["step"]}
        assert on_pult == stepped
        first = row(view, "ПФ-155", "3-банд")
        pult_row = next(r for r in pult["rows"] if r["entity_id"] == first["id"])
        assert pult_row["context"] == "ПФ-155 · 3-банд"
        assert pult_row["target_type"] == "ijro_assignment"

    async def test_inexact_deadlines_never_burn(self, leader_api: AsyncClient) -> None:
        view = await section(leader_api)
        inexact = [item for item in view["items"] if item["due_precision"] != "exact"]

        assert {item["due_precision"] for item in inexact} == {"month", "end_of_year"}
        assert all(item["step"] != "burning" for item in inexact)

    async def test_submitted_and_removed_have_no_step(self, leader_api: AsyncClient) -> None:
        view = await section(leader_api)
        closed = [
            item for item in view["items"] if item["stage"] in {"submitted", "removed_from_control"}
        ]

        assert len(closed) == 6
        assert all(item["step"] is None for item in closed)
        wall = {each["document"]["code"]: each for each in view["documents"]}
        assert sum(each["done"] for each in wall.values()) == 6

    async def test_chronic_counts_extensions(self, leader_api: AsyncClient) -> None:
        view = await section(leader_api)
        chronic = answer(view, Question.CHRONIC)
        licence = row(view, "ЎРҚ-897", "6-модда")

        assert licence["id"] in chronic["rows"]
        assert licence["extensions"] == 2
        history = (await card(leader_api, licence["id"]))["extension_history"]
        assert [each["kind"] for each in history] == ["extension", "extension"]
        assert history[-1]["to"] == licence["due_on"]
        assert licence["original_due_on"] == history[0]["from"]

    async def test_last_batch_and_pending_extension(self, leader_api: AsyncClient) -> None:
        last = answer(await section(leader_api), Question.LAST_BATCH)

        assert last["batch"]["file"] == "АП топшириқлари 3-чорак.docx"
        assert (last["created"], last["changed"], last["vanished"]) == (2, 3, 1)
        assert last["pending_extensions"] == 1
        assert len(last["rows"]) == 5

    async def test_unmatched_spelling_gets_a_suggestion(self, leader_api: AsyncClient) -> None:
        view = await section(leader_api)
        memorandum = row(view, "ВМҚ-512", "1-илова 3-банд")

        assert memorandum["responsible"] is None
        assert memorandum["responsible_raw"] == "Н.Абдуллаева"
        found = await card(leader_api, memorandum["id"])
        assert [person["name"] for person in found["suggestions"]] == ["Абдуллаева Н."]
        assert found["import"]["file"] == "ВМ назорат жадвали.docx"

    async def test_spravka_lists_open_assignments_with_problems(
        self, leader_api: AsyncClient
    ) -> None:
        view = await section(leader_api)
        response = await leader_api.get(f"{IJRO}/spravka")
        assert response.status_code == 200
        lines = response.json()

        report_up = answer(view, Question.REPORT_UP)
        assert [line["id"] for line in lines] == report_up["rows"]
        assert lines[0]["place"].count(" · ") == 1


@pytest.mark.usefixtures("loaded")
class TestMarksAndEdits:
    async def test_both_roles_mark_and_it_is_a_sign_of_life(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        view = await section(leader_api)
        quiet = row(view, "ПФ-155", "9-банд")
        assert quiet["step"] == "silent"

        response = await leader_api.post(
            f"{IJRO}/assignments/{quiet['id']}/marks",
            json={"kind": "doing", "promised_on": (today() + timedelta(days=3)).isoformat()},
        )
        assert response.status_code == 201, response.text
        response = await assistant_api.post(
            f"{IJRO}/assignments/{quiet['id']}/marks", json={"kind": "contacted"}
        )
        assert response.status_code == 201

        after = row(await section(leader_api), "ПФ-155", "9-банд")
        assert after["sign_of_life"] == {"on": today().isoformat(), "source": "control_mark"}
        assert after["step"] is None
        marks = (await card(leader_api, quiet["id"]))["marks"]
        # Множеством: обе отметки теста — одна транзакция и одно `now()` (см. реплики ниже).
        assert {mark["author"] for mark in marks[:2]} == {"assistant", "leader"}

    async def test_a_promise_in_the_past_is_refused(self, leader_api: AsyncClient) -> None:
        target = row(await section(leader_api), "ПФ-155", "9-банд")
        response = await leader_api.post(
            f"{IJRO}/assignments/{target['id']}/marks",
            json={"kind": "doing", "promised_on": (today() - timedelta(days=1)).isoformat()},
        )
        assert response.status_code == 422

    async def test_stage_is_the_assistants_and_goes_by_version(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        target = row(await section(leader_api), "ПҚ-312", "4-банд")
        path = f"{IJRO}/assignments/{target['id']}/stage"

        refused = await leader_api.put(path, json={"stage": "submitted", "version": 1})
        assert refused.status_code == 403
        stale = await assistant_api.put(
            path, json={"stage": "submitted", "version": target["version"] + 1}
        )
        assert stale.status_code == 409
        done = await assistant_api.put(
            path, json={"stage": "submitted", "version": target["version"]}
        )
        assert done.status_code == 204

        after = row(await section(leader_api), "ПҚ-312", "4-банд")
        assert (after["stage"], after["step"]) == ("submitted", None)
        assert after["stage_changed_on"] == today().isoformat()
        assert after["version"] == target["version"] + 1

    async def test_problem_goes_to_the_spravka_and_clears_with_its_proposal(
        self, assistant_api: AsyncClient
    ) -> None:
        target = row(await section(assistant_api), "ПФ-155", "7-банд")
        path = f"{IJRO}/assignments/{target['id']}/problem"

        set_ = await assistant_api.put(
            path,
            json={
                "problem": "  Тест синовлари кечикмоқда  ",
                "proposal": "Хат юбориш",
                "version": 1,
            },
        )
        assert set_.status_code == 204
        lines = (await assistant_api.get(f"{IJRO}/spravka")).json()
        line = next(each for each in lines if each["id"] == target["id"])
        assert (line["problem"], line["proposal"]) == ("Тест синовлари кечикмоқда", "Хат юбориш")

        cleared = await assistant_api.put(
            path, json={"problem": "", "proposal": "Хат юбориш", "version": 2}
        )
        assert cleared.status_code == 204
        found = await card(assistant_api, target["id"])
        assert (found["problem"], found["proposal"], found["problem_updated_on"]) == (
            None,
            None,
            None,
        )

    async def test_extension_request_answers_its_question(self, assistant_api: AsyncClient) -> None:
        view = await section(assistant_api)
        before = answer(view, Question.EXTENSION_REQUESTED)["count"]
        target = row(view, "ПФ-155", "10-банд")

        response = await assistant_api.put(
            f"{IJRO}/assignments/{target['id']}/extension-request",
            json={"value": True, "version": target["version"]},
        )
        assert response.status_code == 204
        after = answer(await section(assistant_api), Question.EXTENSION_REQUESTED)
        assert after["count"] == before + 1
        assert target["id"] in after["rows"]

    async def test_matching_a_spelling_remembers_an_alias(
        self, session: AsyncSession, assistant_api: AsyncClient
    ) -> None:
        view = await section(assistant_api)
        target = row(view, "ВМҚ-512", "1-илова 3-банд")
        person = (await card(assistant_api, target["id"]))["suggestions"][0]

        response = await assistant_api.put(
            f"{IJRO}/assignments/{target['id']}/responsible",
            json={"person_id": person["id"], "version": target["version"]},
        )
        assert response.status_code == 204
        after = row(await section(assistant_api), "ВМҚ-512", "1-илова 3-банд")
        assert after["responsible"] == person
        alias = await session.scalar(
            select(IjroPersonAlias).where(IjroPersonAlias.person_id == uuid.UUID(person["id"]))
        )
        assert alias is not None
        assert alias.source == "manual"

    async def test_both_roles_comment(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        target = row(await section(leader_api), "ПҚ-312", "6-банд")
        path = f"{IJRO}/assignments/{target['id']}/comments"

        assert (await leader_api.post(path, json={"text": "Муддатни сўраймиз"})).status_code == 201
        assert (await assistant_api.post(path, json={"text": "Хат тайёр"})).status_code == 201
        assert (await assistant_api.post(path, json={"text": "   "})).status_code == 422

        comments = (await card(leader_api, target["id"]))["comments"]
        # Множеством, а не списком: обе реплики теста пишутся в одной транзакции, и время у
        # них одно (`now()` — начало транзакции). В бою каждая — свой запрос и свой момент.
        assert {(c["text"], c["author"]) for c in comments} == {
            ("Муддатни сўраймиз", "leader"),
            ("Хат тайёр", "assistant"),
        }


@pytest.mark.usefixtures("loaded")
class TestDecisionsAndTasks:
    async def test_a_question_puts_the_assignment_on_awaiting(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        target = row(await section(assistant_api), "ПФ-155", "10-банд")

        asked = await assistant_api.post(
            "/api/v1/questions",
            json={
                "target_type": "ijro_assignment",
                "target_id": target["id"],
                "text": "Продлить срок?",
            },
        )
        assert asked.status_code == 201, asked.text
        after = row(await section(leader_api), "ПФ-155", "10-банд")
        assert after["step"] == "awaiting_decision"
        assert after["question"]["text"] == "Продлить срок?"

        decided = await leader_api.post(
            "/api/v1/decisions",
            json={"target_type": "ijro_assignment", "target_id": target["id"], "kind": "hurry"},
        )
        assert decided.status_code == 201, decided.text
        final = row(await section(leader_api), "ПФ-155", "10-банд")
        assert final["question"] is None
        assert final["last_decision"]["kind"] == "hurry"

    async def test_decompose_into_a_task(
        self, session: AsyncSession, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        view = await section(assistant_api)
        target = row(view, "ВМҚ-512", "5-банд")
        before = answer(view, Question.WITHOUT_TASKS)
        assert target["id"] in before["rows"]

        prefill = (
            await assistant_api.get(f"{IJRO}/assignments/{target['id']}/task-prefill")
        ).json()
        assert prefill["title"] == (
            "Дастурни амалга ошириш бўйича идоралараро ишчи гуруҳ таркиби тасдиқлансин"
        )
        assert (
            prefill["due_on"]
            == workdays_before(date.fromisoformat(target["due_on"]), 3).isoformat()
        )
        assert prefill["assignee_id"] == target["responsible"]["id"]

        refused = await leader_api.post(f"{IJRO}/assignments/{target['id']}/tasks")
        assert refused.status_code == 403
        created = await assistant_api.post(f"{IJRO}/assignments/{target['id']}/tasks")
        assert created.status_code == 201, created.text
        task = await session.get(Task, uuid.UUID(created.json()["id"]))
        assert task is not None
        assert str(task.ijro_assignment_id) == target["id"]

        after = await section(assistant_api)
        assert target["id"] not in answer(after, Question.WITHOUT_TASKS)["rows"]
        linked = (await card(assistant_api, target["id"]))["linked_tasks"]
        assert [each["code"] for each in linked] == [created.json()["code"]]

    async def test_unknown_assignment_is_not_found(self, leader_api: AsyncClient) -> None:
        response = await leader_api.get(f"{IJRO}/assignments/{uuid.uuid4()}")
        assert response.status_code == 404
