"""API Захвата — обещания экрана, утверждённого заказчиком 28.09.2026.

1. **«Недавние записи»** — последние шесть записей обоих, сначала новые, с автором, сроком
   и тем, куда ушла запись.
2. **Задача** — сразу в «Задачи» тем же путём, что строка «Новая задача», с номером в ответе.
3. **Просьба руководителя** — задача с пометкой «просьба руководителя» в «Задачах» (V17).
4. **Идея, письмо, мероприятие** — во входящие, задач не заводят.
5. **Руководитель записывает свои два типа** — просьбу и идею; остальное — отказ.
6. Поле, которого у типа нет, — отказ, а не молчаливый пропуск; запись — в журнале.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import local_date, now_utc
from app.domain.dictionaries import ProjectStatus
from app.repos.models import AuditLog, Capture, Task, User
from app.services.captures import RECENT_LIMIT
from tests.factories import make_person, make_project

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")
CAPTURES = "/api/v1/captures"
TASKS = "/api/v1/tasks"


def on(days: int) -> date:
    return local_date(now_utc(), TASHKENT) + timedelta(days=days)


async def user_id(session: AsyncSession, role: str) -> Any:
    return await session.scalar(select(User.id).where(User.role == role))


async def count(session: AsyncSession, model: type[Capture] | type[Task]) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def card(api: AsyncClient, task_id: str) -> dict[str, Any]:
    found: list[dict[str, Any]] = [
        item for item in (await api.get(TASKS)).json()["items"] if item["id"] == task_id
    ]
    assert found, "задачи нет в «Задачах»"
    return found[0]


async def written(session: AsyncSession, capture_id: str) -> Capture:
    found = await session.get(Capture, uuid.UUID(capture_id))
    assert found is not None
    return found


class TestReading:
    async def test_recent_newest_first_with_author_and_destination(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        now = datetime.now(UTC)
        leader = await user_id(session, "leader")
        assistant = await user_id(session, "assistant")
        session.add_all(
            [
                Capture(
                    kind="idea",
                    text="Мониторинг пастбищ",
                    author_id=leader,
                    created_at=now - timedelta(hours=26),
                ),
                Capture(
                    kind="letter",
                    text="Минэкологии просит данные по засухе",
                    due_on=on(12),
                    author_id=assistant,
                    created_at=now - timedelta(hours=2),
                ),
            ]
        )
        await session.flush()

        body = (await leader_api.get(CAPTURES)).json()
        assert isinstance(body["is_demo"], bool) and body["as_of"]
        first, second = body["recent"][:2]
        assert (first["kind"], first["author"], first["destination"]) == (
            "letter",
            "assistant",
            "inbox",
        )
        assert first["due_on"] == on(12).isoformat()
        assert (second["kind"], second["author"], second["due_on"]) == ("idea", "leader", None)
        assert "task_code" not in first

    async def test_only_the_last_six(self, leader_api: AsyncClient, session: AsyncSession) -> None:
        now = datetime.now(UTC)
        author = await user_id(session, "assistant")
        session.add_all(
            Capture(
                kind="idea",
                text=f"Идея {hours}",
                author_id=author,
                created_at=now - timedelta(hours=hours),
            )
            for hours in range(1, 9)
        )
        await session.flush()

        recent = (await leader_api.get(CAPTURES)).json()["recent"]
        assert [each["text"] for each in recent] == [f"Идея {hours}" for hours in range(1, 7)]
        assert len(recent) == RECENT_LIMIT

    async def test_nothing_without_a_link(self, api: AsyncClient) -> None:
        assert (await api.get(CAPTURES)).status_code == 401
        assert (await api.post(CAPTURES, json={"kind": "idea", "text": "Идея"})).status_code == 401


class TestTask:
    async def test_task_goes_to_tasks_with_its_fields(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        karimov = await make_person(session, "Каримов А.")
        project = await make_project(session, due_on=on(90), title="Геопортал агентства")

        response = await assistant_api.post(
            CAPTURES,
            json={
                "kind": "task",
                "text": "  Рассмотрение проекта постановления Минэкологии ",
                "due_on": on(4).isoformat(),
                "assignee_id": str(karimov.id),
                "type_code": "review_and_endorse",
                "project_id": str(project.id),
            },
        )
        assert response.status_code == 201
        saved = response.json()
        assert (saved["kind"], saved["destination"], saved["author"]) == (
            "task",
            "tasks",
            "assistant",
        )
        assert saved["text"] == "Рассмотрение проекта постановления Минэкологии"
        assert saved["task_code"].startswith("TSK-")

        capture = await written(session, saved["id"])
        task = await session.get(Task, capture.task_id)
        assert task is not None and task.code == saved["task_code"]
        # Фото из того же касания ложится к задаче — его видно в её карточке.
        assert saved["photo_owner"] == {"owner_type": "task", "owner_id": str(task.id)}
        work = await card(assistant_api, str(task.id))
        assert work["title"] == "Рассмотрение проекта постановления Минэкологии"
        assert (work["due_on"], work["assignee"]["id"], work["project"]["id"]) == (
            on(4).isoformat(),
            str(karimov.id),
            str(project.id),
        )
        assert work["type"]["code"] == "review_and_endorse"
        assert work["is_request"] is False

        recent = (await assistant_api.get(CAPTURES)).json()["recent"]
        assert recent[0]["id"] == saved["id"]

    async def test_recent_shows_the_task_as_it_is_now(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Задачу переименовали и перенесли в «Задачах» — недавние не спорят с ними."""
        saved = (
            await assistant_api.post(
                CAPTURES,
                json={"kind": "task", "text": "Позвонить в Минфин", "due_on": on(2).isoformat()},
            )
        ).json()
        capture = await written(session, saved["id"])
        work = await card(assistant_api, str(capture.task_id))
        edited = await assistant_api.put(
            f"{TASKS}/{work['id']}",
            json={
                "title": "Позвонить в Минфин по смете миссии",
                "type_code": None,
                "due_on": on(9).isoformat(),
                "assignee_id": None,
                "project_id": None,
                "description": None,
                "version": work["version"],
            },
        )
        assert edited.status_code == 204

        first = (await assistant_api.get(CAPTURES)).json()["recent"][0]
        assert (first["id"], first["text"], first["due_on"]) == (
            saved["id"],
            "Позвонить в Минфин по смете миссии",
            on(9).isoformat(),
        )
        # Сказанное при записи осталось в самой записи.
        assert (capture.text, capture.due_on) == ("Позвонить в Минфин", on(2))

    async def test_task_checks_are_the_checks_of_tasks(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        closed = await make_project(session, due_on=on(-30), status=ProjectStatus.DONE)
        before = (await count(session, Capture), await count(session, Task))

        for patch in (
            {"project_id": str(closed.id)},
            {"type_code": "no_such_type"},
            {"due_on": "9999-12-31"},
        ):
            response = await assistant_api.post(
                CAPTURES, json={"kind": "task", "text": "Задача", **patch}
            )
            assert response.status_code == 422, patch
        long = await assistant_api.post(CAPTURES, json={"kind": "task", "text": "з" * 301})
        assert long.status_code == 422
        assert (await count(session, Capture), await count(session, Task)) == before


class TestRequest:
    async def test_request_becomes_a_marked_task(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        karimov = await make_person(session, "Каримов А.")
        response = await leader_api.post(
            CAPTURES,
            json={
                "kind": "request",
                "text": "Справка по паводкам для Кабмина",
                "due_on": on(4).isoformat(),
                "assignee_id": str(karimov.id),
            },
        )
        assert response.status_code == 201
        saved = response.json()
        assert (saved["author"], saved["destination"]) == ("leader", "tasks")

        capture = await written(session, saved["id"])
        work = await card(leader_api, str(capture.task_id))
        assert work["is_request"] is True
        assert work["title"] == "Справка по паводкам для Кабмина"
        assert (work["due_on"], work["assignee"]["id"], work["type"]) == (
            on(4).isoformat(),
            str(karimov.id),
            None,
        )

    async def test_request_has_no_type_or_project(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(90))
        for patch in ({"type_code": "analytical_note"}, {"project_id": str(project.id)}):
            response = await assistant_api.post(
                CAPTURES, json={"kind": "request", "text": "Справка", **patch}
            )
            assert response.status_code == 422, patch


class TestInbox:
    @pytest.mark.parametrize(
        ("kind", "due"),
        [("idea", None), ("letter", 12), ("event", 47)],
    )
    async def test_goes_to_the_inbox_without_a_task(
        self,
        assistant_api: AsyncClient,
        session: AsyncSession,
        kind: str,
        due: int | None,
    ) -> None:
        tasks_before = await count(session, Task)
        body: dict[str, Any] = {"kind": kind, "text": f"  Запись: {kind}  "}
        if due is not None:
            body["due_on"] = on(due).isoformat()

        response = await assistant_api.post(CAPTURES, json=body)
        assert response.status_code == 201
        saved = response.json()
        assert (saved["destination"], saved["task_code"], saved["text"]) == (
            "inbox",
            None,
            f"Запись: {kind}",
        )
        assert saved["due_on"] == (on(due).isoformat() if due is not None else None)
        assert (await written(session, saved["id"])).task_id is None
        assert await count(session, Task) == tasks_before
        # Фото из того же касания (V18): идея — к наброску в «Идеях», письмо и мероприятие —
        # к самой записи во входящих, своих разделов у них ещё нет.
        owner = saved["photo_owner"]
        if kind == "idea":
            assert owner["owner_type"] == "idea"
            assert owner["owner_id"] != saved["id"]
        else:
            assert owner == {"owner_type": "capture", "owner_id": saved["id"]}

    @pytest.mark.parametrize(
        "body",
        [
            {"kind": "idea", "text": "Идея", "due_on": "2026-10-10"},
            {"kind": "letter", "text": "Письмо", "assignee_id": None, "type_code": "other"},
            {"kind": "event", "text": "Мероприятие", "due_on": "9999-12-31"},
            {"kind": "idea", "text": "   "},
            {"kind": "idea", "text": "Идея" + chr(0)},
            {"kind": "idea", "text": "и" * 1001},
            {"kind": "meeting", "text": "Встреча"},
            # Опечатка в имени поля — не запись без срока, а отказ.
            {"kind": "letter", "text": "Письмо", "due": "2026-10-10"},
        ],
    )
    async def test_refused_without_writing(
        self, assistant_api: AsyncClient, session: AsyncSession, body: dict[str, Any]
    ) -> None:
        before = await count(session, Capture)
        assert (await assistant_api.post(CAPTURES, json=body)).status_code == 422
        assert await count(session, Capture) == before


class TestRoles:
    @pytest.mark.parametrize("kind", ["task", "letter", "event"])
    async def test_leader_writes_only_request_and_idea(
        self, leader_api: AsyncClient, session: AsyncSession, kind: str
    ) -> None:
        before = (await count(session, Capture), await count(session, Task))
        response = await leader_api.post(CAPTURES, json={"kind": kind, "text": "Запись"})
        assert response.status_code == 403
        assert (await count(session, Capture), await count(session, Task)) == before

    async def test_capture_is_journaled_with_its_author(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        saved = (await leader_api.post(CAPTURES, json={"kind": "idea", "text": "Идея"})).json()
        entries = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_type == "captures",
                    AuditLog.entity_id == uuid.UUID(saved["id"]),
                )
            )
        )
        assert [entry.action for entry in entries] == ["created"]
        assert entries[0].actor_id == await user_id(session, "leader")
