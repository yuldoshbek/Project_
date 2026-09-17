"""Вехи проекта (ORB-012).

Три критерия карточки. Главный из них — второй: «пропущена» вычисляется, а не хранится.
Хранить её значило бы завести фоновое задание, переписывающее статусы по ночам, и
получить веху, которая целые сутки после срока показывается запланированной. Ровно те
сутки, когда на неё смотрят.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import today_in
from app.domain.dictionaries import Priority, ProjectStatus
from app.domain.milestones import MilestoneState, MilestoneStatus, effective_status
from app.repos.models import AuditLog, Direction, Project

pytestmark = pytest.mark.infra

TODAY = date(2026, 6, 15)
AGENCY_TZ = "Asia/Tashkent"
"""Тот же пояс, в котором наступают сроки у системы (CLAUDE.md, инвариант о времени)."""


class TestMissedIsComputed:
    @pytest.mark.parametrize(
        ("state", "due_on", "expected", "why"),
        [
            (
                MilestoneState.PLANNED,
                TODAY + timedelta(days=1),
                MilestoneStatus.PLANNED,
                "срок впереди",
            ),
            (
                MilestoneState.PLANNED,
                TODAY,
                MilestoneStatus.PLANNED,
                "сегодня срок — ещё не пропущена",
            ),
            (
                MilestoneState.PLANNED,
                TODAY - timedelta(days=1),
                MilestoneStatus.MISSED,
                "срок вчера",
            ),
            (
                MilestoneState.DONE,
                TODAY - timedelta(days=30),
                MilestoneStatus.DONE,
                "закрыли позже срока — всё равно закрыли",
            ),
            (
                MilestoneState.DONE,
                TODAY + timedelta(days=5),
                MilestoneStatus.DONE,
                "закрыли досрочно",
            ),
        ],
    )
    def test_boundaries(
        self, state: MilestoneState, due_on: date, expected: MilestoneStatus, why: str
    ) -> None:
        assert effective_status(state=state, due_on=due_on, today=TODAY) is expected, why

    def test_a_completed_milestone_never_becomes_missed(self) -> None:
        """Веха отвечает на вопрос «сделали ли», а не «успели ли».

        На «успели ли» отвечает сравнение даты закрытия со сроком, и это уже отчётность,
        а не состояние вехи.
        """
        long_overdue = TODAY - timedelta(days=365)
        assert (
            effective_status(state=MilestoneState.DONE, due_on=long_overdue, today=TODAY)
            is MilestoneStatus.DONE
        )

    async def test_the_database_refuses_to_store_the_computed_state(
        self, session: AsyncSession
    ) -> None:
        """Ограничение в базе, а не только соглашение в коде.

        Без него первый же скрипт импорта запишет туда `missed`, и вычисленное значение
        начнёт спорить с хранимым — а разбираться в этом будут через полгода.
        """
        project = await a_project(session)
        savepoint = await session.begin_nested()
        with pytest.raises(Exception, match="state_is_planned_or_done"):
            await session.execute(
                text(
                    "INSERT INTO orbita.milestones (project_id, title, due_on, state, sort_order) "
                    "VALUES (:project_id, 'Подделка', :due_on, 'missed', 1)"
                ),
                {"project_id": project.id, "due_on": TODAY},
            )
        await savepoint.rollback()


async def a_project(session: AsyncSession, **overrides: Any) -> Project:
    direction = await session.scalar(select(Direction).limit(1))
    assert direction is not None
    fields: dict[str, Any] = {
        "code": f"PRJ-2026-{uuid.uuid4().int % 800 + 150:03d}",
        "title": "Проект с вехами",
        "kind": "project",
        "share_externally": True,
        "direction_id": direction.id,
        "status_code": ProjectStatus.IN_PROGRESS.value,
        "priority_code": Priority.NORMAL.value,
        "started_on": date(2026, 1, 1),
        "due_on": date(2026, 12, 31),
    }
    fields.update(overrides)
    project = Project(**fields)
    session.add(project)
    await session.flush()
    return project


def body(**overrides: Any) -> dict[str, Any]:
    """Срок задаётся относительно сегодняшнего дня, а не константой.

    Константа в тестовых данных — мина замедленного действия: набор, написанный в
    сентябре, начинает падать в октябре, и падает он не там, где ошибка.
    """
    payload: dict[str, Any] = {
        "title": "Согласование технического задания",
        "due_on": (today_in(AGENCY_TZ) + timedelta(days=60)).isoformat(),
    }
    payload.update(overrides)
    return payload


class TestLifecycle:
    async def test_a_milestone_is_created_marked_done_and_removed(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)

        created = await assistant_api.post(f"/api/v1/projects/{project.id}/milestones", json=body())
        assert created.status_code == 201, created.text
        assert created.json()["status"] == MilestoneStatus.PLANNED.value
        milestone_id = created.json()["id"]

        done = await assistant_api.patch(
            f"/api/v1/milestones/{milestone_id}", json={"state": MilestoneState.DONE.value}
        )
        assert done.json()["status"] == MilestoneStatus.DONE.value

        assert (await assistant_api.delete(f"/api/v1/milestones/{milestone_id}")).status_code == 204
        listed = await assistant_api.get(f"/api/v1/projects/{project.id}/milestones")
        assert listed.json() == []

    async def test_a_past_deadline_shows_as_missed_without_anyone_touching_it(
        self, assistant_api: AsyncClient, session: AsyncSession, settings: Any
    ) -> None:
        project = await a_project(session)
        past = (today_in(settings.timezone) - timedelta(days=3)).isoformat()

        created = await assistant_api.post(
            f"/api/v1/projects/{project.id}/milestones", json=body(due_on=past)
        )

        assert created.json()["status"] == MilestoneStatus.MISSED.value
        assert created.json()["state"] == MilestoneState.PLANNED.value, (
            "хранимое состояние обязано остаться прежним"
        )

    async def test_milestones_of_a_missing_project_are_not_found(
        self, assistant_api: AsyncClient
    ) -> None:
        """404, а не пустой список: опечатка в адресе не должна выглядеть как «вех нет»."""
        response = await assistant_api.get(f"/api/v1/projects/{uuid.uuid4()}/milestones")

        assert response.status_code == 404


class TestOrder:
    async def test_new_milestones_keep_the_order_of_adding(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        for title, due in (("Первая", "2026-09-01"), ("Вторая", "2026-08-01")):
            await assistant_api.post(
                f"/api/v1/projects/{project.id}/milestones", json=body(title=title, due_on=due)
            )

        listed = await assistant_api.get(f"/api/v1/projects/{project.id}/milestones")

        assert [item["title"] for item in listed.json()] == ["Первая", "Вторая"], (
            "порядок задаёт человек, а не срок: согласование идёт раньше подписания"
        )

    async def test_the_order_is_rearranged_as_a_whole(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        ids = []
        for title in ("Первая", "Вторая", "Третья"):
            created = await assistant_api.post(
                f"/api/v1/projects/{project.id}/milestones", json=body(title=title)
            )
            ids.append(created.json()["id"])

        reordered = await assistant_api.put(
            f"/api/v1/projects/{project.id}/milestones/order",
            json={"milestone_ids": [ids[2], ids[0], ids[1]]},
        )

        assert reordered.status_code == 200
        assert [item["title"] for item in reordered.json()] == ["Третья", "Первая", "Вторая"]

        listed = await assistant_api.get(f"/api/v1/projects/{project.id}/milestones")
        assert [item["title"] for item in listed.json()] == ["Третья", "Первая", "Вторая"]

    async def test_an_order_that_lost_a_milestone_is_refused(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Перетаскивание, начатое до удаления вехи, не должно применяться наполовину.

        Иначе часть вех остаётся с прежним порядком, и список после перезагрузки
        выглядит иначе, чем только что на экране.
        """
        project = await a_project(session)
        ids = []
        for title in ("Первая", "Вторая"):
            created = await assistant_api.post(
                f"/api/v1/projects/{project.id}/milestones", json=body(title=title)
            )
            ids.append(created.json()["id"])

        refused = await assistant_api.put(
            f"/api/v1/projects/{project.id}/milestones/order",
            json={"milestone_ids": [ids[0]]},
        )

        assert refused.status_code == 422
        assert "состав" in refused.json()["detail"]


class TestMiniProjects:
    async def test_a_mini_project_lives_without_milestones(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Требовать вехи от недельной работы — значит заставить их придумать."""
        mini = await a_project(session, kind="mini")

        listed = await assistant_api.get(f"/api/v1/projects/{mini.id}/milestones")

        assert listed.status_code == 200
        assert listed.json() == []

    async def test_but_a_mini_project_may_have_one_if_it_wants(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """«Необязательны» — не «запрещены».

        Запрет заставил бы менять вид проекта ради одной контрольной точки.
        """
        mini = await a_project(session, kind="mini")

        created = await assistant_api.post(f"/api/v1/projects/{mini.id}/milestones", json=body())

        assert created.status_code == 201


class TestWhoMayWrite:
    async def test_leader_reads_but_changes_nothing(
        self, leader_api: AsyncClient, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        created = await assistant_api.post(f"/api/v1/projects/{project.id}/milestones", json=body())
        milestone_id = created.json()["id"]

        assert (
            await leader_api.get(f"/api/v1/projects/{project.id}/milestones")
        ).status_code == 200
        assert (
            await leader_api.post(f"/api/v1/projects/{project.id}/milestones", json=body())
        ).status_code == 403
        assert (
            await leader_api.patch(f"/api/v1/milestones/{milestone_id}", json={"title": "Правка"})
        ).status_code == 403
        assert (await leader_api.delete(f"/api/v1/milestones/{milestone_id}")).status_code == 403
        assert (
            await leader_api.put(
                f"/api/v1/projects/{project.id}/milestones/order",
                json={"milestone_ids": [milestone_id]},
            )
        ).status_code == 403


class TestJournal:
    async def test_changing_a_milestone_leaves_a_trail(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        created = await assistant_api.post(f"/api/v1/projects/{project.id}/milestones", json=body())
        milestone_id = uuid.UUID(created.json()["id"])

        await assistant_api.patch(
            f"/api/v1/milestones/{milestone_id}", json={"state": MilestoneState.DONE.value}
        )

        entries = list(
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.entity_id == milestone_id)
                .order_by(AuditLog.occurred_at)
            )
        )
        assert [entry.action for entry in entries] == ["created", "updated"]
        assert entries[1].changes["state"]["to"] == MilestoneState.DONE.value

    async def test_a_missing_milestone_is_not_found(self, assistant_api: AsyncClient) -> None:
        response = await assistant_api.patch(
            f"/api/v1/milestones/{uuid.uuid4()}", json={"title": "Нет такой"}
        )

        assert response.status_code == 404
