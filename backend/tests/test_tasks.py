"""API раздела «Задачи» — обещания экрана, утверждённого заказчиком 27.09.2026.

1. **Одни числа с Пультом** (инвариант 2): ступень задачи — строка той же лестницы; «кто
   перегружен» — по тем же строкам.
2. **Новая задача строкой** (критерий ТЗ 11): разбор даёт тип, срок и ответственного и
   ничего не пишет; обязательное поле у задачи одно — название.
3. **Статус — по графу переходов**, отметки времени ставит система.
4. **Отметка пункта чек-листа — признак жизни задачи.**
5. Правка по устаревшей версии — честный отказ (инвариант 15); вносит помощник.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import local_date, now_utc
from app.domain.dictionaries import ProjectStatus, TaskStatus
from app.domain.tasks import DUE_TIME
from app.repos.models import AuditLog, LeaderQuestion, Task, TaskChecklistItem
from tests.factories import make_person, make_project, make_task

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")
TASKS = "/api/v1/tasks"


def today() -> date:
    return local_date(now_utc(), TASHKENT)


def on(days: int) -> date:
    return today() + timedelta(days=days)


def due(days: int) -> datetime:
    """Срок задачи так, как его хранит система: конец рабочего дня по Ташкенту, в UTC."""
    return datetime.combine(on(days), DUE_TIME, TASHKENT).astimezone(UTC)


def card_of(body: dict[str, Any], task: Task) -> dict[str, Any]:
    found: list[dict[str, Any]] = [item for item in body["items"] if item["id"] == str(task.id)]
    assert found, f"задачи {task.title} нет в ответе"
    return found[0]


async def audit_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(AuditLog)) or 0


class TestReading:
    async def test_steps_are_the_pult_steps(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        overdue = await make_task(session, due_at=due(-2))
        burning = await make_task(session, due_at=due(3))
        await make_task(session, due_at=due(60))

        tasks = (await leader_api.get(TASKS)).json()
        pult = (await leader_api.get("/api/v1/pult")).json()
        on_pult = {
            row["entity_id"]: (row["step"], row["deviation"])
            for row in pult["rows"]
            if row["section"] == "tasks"
        }
        for item in tasks["items"]:
            if item["step"] is None:
                assert item["id"] not in on_pult
            else:
                assert on_pult[item["id"]] == (item["step"], item["deviation"])
        assert card_of(tasks, overdue)["step"] == "overdue"
        assert card_of(tasks, burning)["step"] == "burning"

    async def test_horizons_and_order(self, leader_api: AsyncClient, session: AsyncSession) -> None:
        later = await make_task(session, due_at=due(30), title="Позже")
        none = await make_task(session, due_at=None, title="Без срока")
        overdue = await make_task(session, due_at=due(-1), title="Просрочена")
        tomorrow = await make_task(session, due_at=due(1), title="Завтра")
        closed = await make_task(session, due_at=due(-5), title="Закрыта")
        closed.status = TaskStatus.DONE.value
        closed.completed_at = now_utc()
        await session.flush()

        body = (await leader_api.get(TASKS)).json()
        horizons = {
            task.title: card_of(body, task)["horizon"]
            for task in (later, none, overdue, tomorrow, closed)
        }
        assert horizons == {
            "Позже": "later",
            "Без срока": "none",
            "Просрочена": "overdue",
            "Завтра": "tomorrow",
            "Закрыта": "closed",
        }
        ids = [item["id"] for item in body["items"]]
        order = [ids.index(str(task.id)) for task in (overdue, tomorrow, later, none, closed)]
        assert order == sorted(order)
        assert card_of(body, tomorrow)["due_on"] == on(1).isoformat()

    async def test_load_counts_the_rows(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """«Кто перегружен?» — у человека столько просроченного, сколько его строк в списке."""
        busy = await make_person(session, "Перегруженный П.")
        for days in (-3, -1, 2, 40):
            await make_task(session, due_at=due(days), assignee=busy)

        body = (await leader_api.get(TASKS)).json()
        row = next(item for item in body["load"] if item["person"]["id"] == str(busy.id))
        own = [item for item in body["items"] if (item["assignee"] or {}).get("id") == str(busy.id)]
        assert row == {
            "person": {"id": str(busy.id), "name": "Перегруженный П."},
            "overdue": sum(item["step"] == "overdue" for item in own),
            "burning": sum(item["step"] == "burning" for item in own),
            "open": len(own),
        }
        assert (row["overdue"], row["burning"], row["open"]) == (2, 1, 4)

    async def test_task_of_a_closed_project_leaves_the_ladder(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(-10), status=ProjectStatus.DONE)
        person = await make_person(session, "Закрытый П.")
        task = await make_task(session, due_at=due(-3), project=project, assignee=person)

        body = (await leader_api.get(TASKS)).json()
        assert card_of(body, task)["step"] is None
        assert all(item["person"]["id"] != str(person.id) for item in body["load"])

    async def test_moves_checklist_and_links(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(90))
        task = await make_task(session, due_at=due(10), project=project)
        for days in (20, 15, 30):
            task.due_at = due(days)
            await session.flush()
        session.add_all(
            [
                TaskChecklistItem(task_id=task.id, text="Первый", is_done=True, sort_order=1),
                TaskChecklistItem(task_id=task.id, text="Второй", is_done=False, sort_order=2),
            ]
        )
        await session.flush()

        card = card_of((await leader_api.get(TASKS)).json(), task)
        assert card["moves"] == 2
        assert card["original_due_on"] == on(10).isoformat()
        assert card["checklist"] == {"done": 1, "total": 2}
        assert card["project"] == {
            "id": str(project.id),
            "code": project.code,
            "title": project.title,
        }
        assert card["ijro"] is None

    async def test_form_dictionaries(self, leader_api: AsyncClient, session: AsyncSession) -> None:
        body = (await leader_api.get(TASKS)).json()
        assert len(body["types"]) == 11
        assert body["is_demo"] is True
        closed = await make_project(session, due_on=on(-5), status=ProjectStatus.CANCELLED)
        body = (await leader_api.get(TASKS)).json()
        assert str(closed.id) not in {ref["id"] for ref in body["projects"]}

    async def test_requires_a_session(self, api: AsyncClient) -> None:
        assert (await api.get(TASKS)).status_code == 401


class TestDetail:
    async def test_card(self, leader_api: AsyncClient, session: AsyncSession) -> None:
        task = await make_task(session, due_at=due(5))
        session.add(TaskChecklistItem(task_id=task.id, text="Пункт", sort_order=1))
        session.add(LeaderQuestion(target_type="task", target_id=task.id, text="Утвердить?"))
        await session.flush()

        body = (await leader_api.get(f"{TASKS}/{task.id}")).json()
        assert body["step"] == "awaiting_decision"
        assert body["question"]["text"] == "Утвердить?"
        assert [item["text"] for item in body["checklist_items"]] == ["Пункт"]
        assert body["transitions"] == ["new", "in_review", "done", "cancelled"]

    async def test_unknown(self, leader_api: AsyncClient) -> None:
        response = await leader_api.get(f"{TASKS}/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestParse:
    async def test_example_from_the_spec_writes_nothing(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        karimov = await make_person(session, "Каримов А.")
        journal = await audit_count(session)

        response = await leader_api.post(
            f"{TASKS}/parse",
            json={"text": "к пятнице рассмотрение проекта постановления Минэкологии, Каримов"},
        )
        assert response.status_code == 200, response.text
        body = response.json()

        friday = on(((4 - today().weekday()) % 7) or 7)
        assert body == {
            "title": "Рассмотрение проекта постановления Минэкологии",
            "type_code": "review_and_endorse",
            "due_on": friday.isoformat(),
            "assignee_id": str(karimov.id),
            "matched": {"type": "рассмотр", "due": "к пятнице", "assignee": "Каримов"},
        }
        assert await audit_count(session) == journal


class TestCreate:
    async def test_title_only(self, assistant_api: AsyncClient, session: AsyncSession) -> None:
        response = await assistant_api.post(TASKS, json={"title": "  Позвонить в Минфин  "})
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["title"] == "Позвонить в Минфин"
        assert body["status"] == "new"
        assert body["code"].startswith(f"TSK-{today().year}-")
        assert body["due_on"] is None
        assert body["project"] is None
        assert body["horizon"] == "none"

    async def test_full_line_result(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        person = await make_person(session, "Рахимов Ш.")
        project = await make_project(session, due_on=on(90))

        body = (
            await assistant_api.post(
                TASKS,
                json={
                    "title": "Справка по паводкам",
                    "type_code": "analytical_note",
                    "due_on": on(1).isoformat(),
                    "assignee_id": str(person.id),
                    "project_id": str(project.id),
                },
            )
        ).json()
        assert body["due_on"] == on(1).isoformat()
        assert body["original_due_on"] == on(1).isoformat()
        assert body["horizon"] == "tomorrow"
        assert body["type"]["code"] == "analytical_note"
        assert body["assignee"]["id"] == str(person.id)

        stored = await session.get(Task, body["id"])
        assert stored is not None and stored.due_at is not None
        assert stored.due_at.astimezone(TASHKENT).time() == DUE_TIME

    @pytest.mark.parametrize(
        ("patch", "status_code"),
        [
            ({"title": "   "}, 422),
            ({"title": "Задача" + chr(0)}, 422),
            ({"type_code": "no_such_type"}, 422),
            ({"due_on": "9999-12-31"}, 422),
            ({"assignee_id": "00000000-0000-0000-0000-000000000000"}, 404),
            ({"project_id": "00000000-0000-0000-0000-000000000000"}, 404),
        ],
    )
    async def test_refusals(
        self, assistant_api: AsyncClient, patch: dict[str, str], status_code: int
    ) -> None:
        response = await assistant_api.post(TASKS, json={"title": "Задача", **patch})
        assert response.status_code == status_code, response.text

    async def test_closed_project(self, assistant_api: AsyncClient, session: AsyncSession) -> None:
        project = await make_project(session, due_on=on(-5), status=ProjectStatus.DONE)
        response = await assistant_api.post(
            TASKS, json={"title": "Задача", "project_id": str(project.id)}
        )
        assert response.status_code == 422

    async def test_leader_cannot(self, leader_api: AsyncClient) -> None:
        assert (await leader_api.post(TASKS, json={"title": "Задача"})).status_code == 403


class TestEdit:
    async def test_later_due_is_a_move(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        task = await make_task(session, due_at=due(5))
        response = await assistant_api.put(
            f"{TASKS}/{task.id}",
            json={
                "title": "Уточнённая задача",
                "due_on": on(12).isoformat(),
                "description": "  Подробности  ",
                "version": task.version,
            },
        )
        assert response.status_code == 204, response.text

        card = card_of((await assistant_api.get(TASKS)).json(), task)
        assert card["title"] == "Уточнённая задача"
        assert card["due_on"] == on(12).isoformat()
        assert card["original_due_on"] == on(5).isoformat()
        assert card["moves"] == 1
        detail = (await assistant_api.get(f"{TASKS}/{task.id}")).json()
        assert detail["description"] == "Подробности"

    async def test_first_due_becomes_original(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        task = await make_task(session, due_at=None)
        await assistant_api.put(
            f"{TASKS}/{task.id}",
            json={"title": task.title, "due_on": on(3).isoformat(), "version": task.version},
        )
        card = card_of((await assistant_api.get(TASKS)).json(), task)
        assert card["original_due_on"] == on(3).isoformat()
        assert card["moves"] == 0

    async def test_stale_version(self, assistant_api: AsyncClient, session: AsyncSession) -> None:
        task = await make_task(session, due_at=due(5))
        seen = task.version
        task.title = "Переименована в соседней вкладке"
        await session.flush()
        response = await assistant_api.put(
            f"{TASKS}/{task.id}", json={"title": "Поверх", "version": seen}
        )
        assert response.status_code == 409
        assert response.json()["type"].endswith("stale-data")


class TestStatus:
    async def test_graph_and_stamps(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        task = await make_task(session, due_at=due(5))
        task.status = TaskStatus.NEW.value
        await session.flush()
        url = f"{TASKS}/{task.id}/status"

        # Из «новой» сразу в «готова» нельзя: учёт показал бы сделанным несделанное.
        refused = await assistant_api.put(url, json={"status": "done", "version": task.version})
        assert refused.status_code == 409

        started = await assistant_api.put(
            url, json={"status": "in_progress", "version": task.version}
        )
        assert started.status_code == 204
        await session.refresh(task)
        assert task.started_at is not None

        await assistant_api.put(url, json={"status": "done", "version": task.version})
        await session.refresh(task)
        assert task.status == "done" and task.completed_at is not None

        await assistant_api.put(url, json={"status": "in_progress", "version": task.version})
        await session.refresh(task)
        assert task.completed_at is None

    async def test_leader_cannot(self, leader_api: AsyncClient, session: AsyncSession) -> None:
        task = await make_task(session, due_at=due(5))
        response = await leader_api.put(
            f"{TASKS}/{task.id}/status", json={"status": "in_review", "version": task.version}
        )
        assert response.status_code == 403


class TestChecklist:
    async def test_add_toggle_remove(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        task = await make_task(session, due_at=due(20))
        base = f"{TASKS}/{task.id}/checklist"

        created = await assistant_api.post(base, json={"text": "  Письмо в хокимият  "})
        assert created.status_code == 201, created.text
        item_id = created.json()["id"]
        detail = (await assistant_api.get(f"{TASKS}/{task.id}")).json()
        item = detail["checklist_items"][0]
        assert item["text"] == "Письмо в хокимият"

        toggled = await assistant_api.put(
            f"{base}/{item_id}", json={"is_done": True, "version": item["version"]}
        )
        assert toggled.status_code == 204
        stale = await assistant_api.put(
            f"{base}/{item_id}", json={"is_done": False, "version": item["version"]}
        )
        assert stale.status_code == 409

        version = (await assistant_api.get(f"{TASKS}/{task.id}")).json()["checklist_items"][0][
            "version"
        ]
        removed = await assistant_api.delete(f"{base}/{item_id}", params={"version": version})
        assert removed.status_code == 204
        assert (await assistant_api.get(f"{TASKS}/{task.id}")).json()["checklist_items"] == []

    async def test_ticking_an_item_is_a_sign_of_life(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Задачу без правок три недели, по которой отметили пункт, — не молчит."""
        task = await make_task(session, due_at=due(60))
        item = TaskChecklistItem(task_id=task.id, text="Пункт", sort_order=1)
        session.add(item)
        await session.flush()
        long_ago = now_utc() - timedelta(days=21)
        await session.execute(
            update(Task).where(Task.id == task.id).values(created_at=long_ago, updated_at=None)
        )
        await session.execute(
            update(TaskChecklistItem)
            .where(TaskChecklistItem.id == item.id)
            .values(created_at=long_ago, updated_at=None)
        )
        assert card_of((await assistant_api.get(TASKS)).json(), task)["step"] == "silent"

        await session.refresh(item)
        await assistant_api.put(
            f"{TASKS}/{task.id}/checklist/{item.id}",
            json={"is_done": True, "version": item.version},
        )
        assert card_of((await assistant_api.get(TASKS)).json(), task)["step"] is None

    async def test_empty_item_and_leader(
        self, assistant_api: AsyncClient, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        task = await make_task(session, due_at=due(20))
        base = f"{TASKS}/{task.id}/checklist"
        assert (await assistant_api.post(base, json={"text": "   "})).status_code == 422
        assert (await leader_api.post(base, json={"text": "Пункт"})).status_code == 403
