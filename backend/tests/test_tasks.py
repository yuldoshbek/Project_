"""Задачи (ORB-014).

Шесть критериев карточки плюс одно, что в ней не записано: правило просрочки живёт на
двух языках — в домене и в SQL, — и они обязаны совпадать. Совпадение проверяется не
чтением кода, а сверкой: отфильтрованный базой список сравнивается с признаком,
посчитанным в Python. Разойдись они — и число просроченных на дашборде перестанет
сходиться с тем, что видно в карточке.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dictionaries import Priority, ProjectStatus, TaskStatus
from app.domain.errors import ConflictError
from app.domain.tasks import days_overdue, is_overdue, validate_transition
from app.repos.models import AuditLog, Direction, Person, Project, Task

pytestmark = pytest.mark.infra

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


class TestOverdueIsComputed:
    """[ADR-0004](../../docs/adr/ADR-0004-overdue-is-computed.md)."""

    @pytest.mark.parametrize(
        ("due_at", "status", "expected", "why"),
        [
            (None, TaskStatus.NEW, False, "срок не назначали — он и не наступает"),
            (NOW + timedelta(hours=1), TaskStatus.NEW, False, "срок впереди"),
            (NOW, TaskStatus.IN_PROGRESS, False, "ровно сейчас — ещё не «раньше»"),
            (NOW - timedelta(minutes=1), TaskStatus.IN_PROGRESS, True, "минута после срока"),
            (NOW - timedelta(days=5), TaskStatus.DONE, False, "выполнена — просрочка снята"),
            (NOW - timedelta(days=5), TaskStatus.CANCELLED, False, "отменена — просрочки нет"),
        ],
    )
    def test_boundaries(
        self, due_at: datetime | None, status: TaskStatus, expected: bool, why: str
    ) -> None:
        assert is_overdue(due_at=due_at, status=status, now=NOW) is expected, why

    def test_days_are_full_days_not_a_calendar_flip(self) -> None:
        """Ноль — «не набежало суток», а не «не просрочена».

        Признак и число отвечают на разные вопросы: первый показывается маркером,
        второе — пояснением к нему.
        """
        just_late = NOW - timedelta(hours=2)
        assert is_overdue(due_at=just_late, status=TaskStatus.NEW, now=NOW) is True
        assert days_overdue(due_at=just_late, status=TaskStatus.NEW, now=NOW) == 0
        assert days_overdue(due_at=NOW - timedelta(days=3), status=TaskStatus.NEW, now=NOW) == 3

    def test_a_completed_task_has_no_days_overdue(self) -> None:
        assert days_overdue(due_at=NOW - timedelta(days=9), status=TaskStatus.DONE, now=NOW) == 0


class TestStatusTransitions:
    def test_a_completed_task_cannot_become_new_again(self) -> None:
        """Прямо из критерия приёмки: работа, которую делали, не становится неначатой."""
        with pytest.raises(ConflictError):
            validate_transition(current=TaskStatus.DONE, target=TaskStatus.NEW)

    def test_but_it_can_be_reopened_through_work(self) -> None:
        validate_transition(current=TaskStatus.DONE, target=TaskStatus.IN_PROGRESS)
        validate_transition(current=TaskStatus.IN_PROGRESS, target=TaskStatus.NEW)

    def test_a_new_task_cannot_be_declared_done_at_once(self) -> None:
        """Иначе учёт показывает выполненными задачи, которых никто не делал."""
        with pytest.raises(ConflictError):
            validate_transition(current=TaskStatus.NEW, target=TaskStatus.DONE)

    def test_repeating_the_same_status_is_allowed(self) -> None:
        """Одно изменение, посланное дважды, не должно отличаться от посланного раз."""
        validate_transition(current=TaskStatus.DONE, target=TaskStatus.DONE)

    def test_the_refusal_names_where_one_can_go(self) -> None:
        with pytest.raises(ConflictError) as refused:
            validate_transition(current=TaskStatus.NEW, target=TaskStatus.DONE)

        assert "in_progress" in (refused.value.detail or "")


async def a_project(session: AsyncSession, **overrides: Any) -> Project:
    direction = await session.scalar(select(Direction).limit(1))
    assert direction is not None
    project = Project(
        code=f"PRJ-2026-{uuid.uuid4().int % 900 + 99:03d}",
        title="Проект для задач",
        kind="project",
        classification="internal",
        direction_id=direction.id,
        status_code=ProjectStatus.IN_PROGRESS.value,
        priority_code=Priority.NORMAL.value,
        started_on=date(2026, 1, 1),
        due_on=date(2026, 12, 31),
        **overrides,
    )
    session.add(project)
    await session.flush()
    return project


def body(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": "Подготовить справку по мониторингу",
        "priority_code": Priority.NORMAL.value,
    }
    payload.update(overrides)
    return payload


class TestTasksLiveWithAndWithoutProjects:
    async def test_a_task_can_exist_outside_a_project(self, assistant_api: AsyncClient) -> None:
        """Половина работы аппарата — поручения, у которых проекта нет и не будет."""
        created = await assistant_api.post("/api/v1/tasks", json=body())

        assert created.status_code == 201, created.text
        assert created.json()["project_id"] is None

    async def test_a_task_can_belong_to_a_project(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)

        created = await assistant_api.post("/api/v1/tasks", json=body(project_id=str(project.id)))

        assert created.status_code == 201
        assert created.json()["project_id"] == str(project.id)

    async def test_tasks_outside_projects_can_be_listed_separately(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        await assistant_api.post("/api/v1/tasks", json=body(title="Без проекта"))
        await assistant_api.post(
            "/api/v1/tasks", json=body(title="С проектом", project_id=str(project.id))
        )

        loose = await assistant_api.get("/api/v1/tasks", params={"without_project": True})

        assert [item["title"] for item in loose.json()] == ["Без проекта"]


class TestAssigneeIsAnEmployeeNotAUser:
    async def test_the_assignee_comes_from_the_staff_directory(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Исполнитель — сотрудник агентства, а не пользователь системы (ADR-0011).

        Пользователей двое, исполнителей десятки: сослаться на пользователя означало бы
        завести сорок учётных записей, которыми никто не воспользуется.
        """
        person = Person(full_name="Отабек Сафаров", position="Ведущий специалист")
        session.add(person)
        await session.flush()

        created = await assistant_api.post(
            "/api/v1/tasks", json=body(assignee_person_id=str(person.id))
        )

        assert created.status_code == 201
        assert created.json()["assignee_person_id"] == str(person.id)

    async def test_a_user_identifier_is_not_accepted_as_an_assignee(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Ссылка ведёт в `people`, и база это подтверждает, а не только соглашение."""
        from app.repos.models import User

        user = await session.scalar(select(User).limit(1))
        assert user is not None

        created = await assistant_api.post(
            "/api/v1/tasks", json=body(assignee_person_id=str(user.id))
        )

        assert created.status_code >= 400, "пользователь прошёл как исполнитель"


class TestTimestampsAreSetBySystem:
    async def test_going_to_work_records_the_start_and_finishing_records_the_end(
        self, assistant_api: AsyncClient
    ) -> None:
        created = await assistant_api.post("/api/v1/tasks", json=body())
        task_id = created.json()["id"]
        assert created.json()["started_at"] is None

        started = await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.IN_PROGRESS.value}
        )
        assert started.json()["started_at"] is not None

        done = await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.DONE.value}
        )
        assert done.json()["completed_at"] is not None
        assert done.json()["is_overdue"] is False

    async def test_reopening_clears_the_completion_mark(self, assistant_api: AsyncClient) -> None:
        """Иначе задача остаётся выполненной в отчётах и незакрытой на экране разом."""
        created = await assistant_api.post("/api/v1/tasks", json=body())
        task_id = created.json()["id"]

        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.IN_PROGRESS.value}
        )
        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.DONE.value}
        )
        reopened = await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.IN_PROGRESS.value}
        )

        assert reopened.json()["completed_at"] is None

    async def test_a_forbidden_transition_is_refused_through_the_api(
        self, assistant_api: AsyncClient
    ) -> None:
        created = await assistant_api.post("/api/v1/tasks", json=body())
        task_id = created.json()["id"]
        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.IN_PROGRESS.value}
        )
        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.DONE.value}
        )

        refused = await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.NEW.value}
        )

        assert refused.status_code == 409
        assert refused.json()["type"].endswith("conflict")


class TestOverdueFilterMatchesTheComputedFlag:
    async def test_the_two_languages_agree(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Правило просрочки записано в домене и в SQL. Сверяем, а не верим.

        Разойдись они — число просроченных на дашборде перестанет сходиться с тем, что
        видно в карточке, и доверия не будет ни к одному экрану.
        """
        past = datetime.now(UTC) - timedelta(days=2)
        future = datetime.now(UTC) + timedelta(days=2)

        await assistant_api.post("/api/v1/tasks", json=body(title="Горит", due_at=past.isoformat()))
        await assistant_api.post(
            "/api/v1/tasks", json=body(title="Успеваем", due_at=future.isoformat())
        )
        await assistant_api.post("/api/v1/tasks", json=body(title="Без срока"))
        closed = await assistant_api.post(
            "/api/v1/tasks", json=body(title="Закрыта", due_at=past.isoformat())
        )
        closed_id = closed.json()["id"]
        await assistant_api.patch(
            f"/api/v1/tasks/{closed_id}", json={"status": TaskStatus.IN_PROGRESS.value}
        )
        await assistant_api.patch(
            f"/api/v1/tasks/{closed_id}", json={"status": TaskStatus.DONE.value}
        )

        everything = (await assistant_api.get("/api/v1/tasks")).json()
        by_flag = sorted(item["title"] for item in everything if item["is_overdue"])
        by_filter = sorted(
            item["title"]
            for item in (await assistant_api.get("/api/v1/tasks", params={"overdue": True})).json()
        )

        assert by_flag == by_filter == ["Горит"]

        not_overdue = sorted(
            item["title"]
            for item in (await assistant_api.get("/api/v1/tasks", params={"overdue": False})).json()
        )
        assert not_overdue == ["Без срока", "Закрыта", "Успеваем"]

    async def test_the_overdue_filter_uses_its_index(self, session: AsyncSession) -> None:
        """Критерий приёмки требует подтвердить индекс планом запроса, а не верой.

        План снимается на пустой таблице, поэтому проверяется не выбор плана —
        планировщик на десятке строк честно предпочтёт последовательный просмотр, — а то,
        что индекс существует и покрывает нужные столбцы в нужном порядке. Замер выбора
        плана на боевом объёме — ORB-051.
        """
        rows = list(
            await session.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'orbita' AND tablename = 'tasks' "
                    "AND indexname = 'ix_tasks_status_due_at'"
                )
            )
        )
        assert rows, "индекс (status, due_at) из критерия приёмки отсутствует"
        assert "(status, due_at)" in rows[0][0], rows[0][0]

        plan = await session.execute(
            text(
                "EXPLAIN SELECT id FROM orbita.tasks "
                "WHERE due_at < now() AND status NOT IN ('done', 'cancelled')"
            )
        )
        assert plan.scalars().all(), "план запроса не получен"


class TestAutoProgress:
    """Перенесено из ORB-011: подключать расчёт было не к чему, пока не было задач."""

    async def test_closing_a_task_moves_the_project_percentage(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        first = await assistant_api.post(
            "/api/v1/tasks", json=body(title="Первая", project_id=str(project.id))
        )
        await assistant_api.post(
            "/api/v1/tasks", json=body(title="Вторая", project_id=str(project.id))
        )

        await session.refresh(project)
        assert project.progress_pct == 0

        task_id = first.json()["id"]
        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.IN_PROGRESS.value}
        )
        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.DONE.value}
        )

        await session.refresh(project)
        assert project.progress_pct == 50

    async def test_the_manual_percentage_is_never_overwritten(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Иначе цифра куратора молча затиралась бы после каждой закрытой задачи."""
        project = await a_project(session, progress_mode="manual", progress_pct=70)
        created = await assistant_api.post("/api/v1/tasks", json=body(project_id=str(project.id)))
        task_id = created.json()["id"]

        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.IN_PROGRESS.value}
        )
        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.DONE.value}
        )

        await session.refresh(project)
        assert project.progress_pct == 70

    async def test_moving_a_task_away_recounts_the_project_it_left(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Иначе у прежнего процент остаётся посчитанным по задаче, которой у него нет."""
        source = await a_project(session)
        target = await a_project(session)

        created = await assistant_api.post("/api/v1/tasks", json=body(project_id=str(source.id)))
        task_id = created.json()["id"]
        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.IN_PROGRESS.value}
        )
        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.DONE.value}
        )
        await session.refresh(source)
        assert source.progress_pct == 100

        await assistant_api.patch(f"/api/v1/tasks/{task_id}", json={"project_id": str(target.id)})

        await session.refresh(source)
        await session.refresh(target)
        assert source.progress_pct == 0, "процент остался посчитанным по чужой задаче"
        assert target.progress_pct == 100

    async def test_deleting_the_last_task_returns_the_project_to_zero(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        created = await assistant_api.post("/api/v1/tasks", json=body(project_id=str(project.id)))
        task_id = created.json()["id"]
        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.IN_PROGRESS.value}
        )
        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.DONE.value}
        )

        await assistant_api.delete(f"/api/v1/tasks/{task_id}")

        await session.refresh(project)
        assert project.progress_pct == 0, "пустота не является завершённостью"


class TestWhoMayWrite:
    async def test_leader_reads_but_changes_nothing(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        created = await assistant_api.post("/api/v1/tasks", json=body())
        task_id = created.json()["id"]

        assert (await leader_api.get("/api/v1/tasks")).status_code == 200
        assert (await leader_api.post("/api/v1/tasks", json=body())).status_code == 403
        assert (
            await leader_api.patch(f"/api/v1/tasks/{task_id}", json={"title": "Правка"})
        ).status_code == 403
        assert (await leader_api.delete(f"/api/v1/tasks/{task_id}")).status_code == 403


class TestListingAndCode:
    async def test_numbers_run_in_sequence_with_five_digits(
        self, assistant_api: AsyncClient
    ) -> None:
        first = await assistant_api.post("/api/v1/tasks", json=body())
        second = await assistant_api.post("/api/v1/tasks", json=body())

        codes = [first.json()["code"], second.json()["code"]]
        assert all(code.startswith("TSK-") for code in codes), codes
        assert len(codes[0].split("-")[-1]) == 5
        assert int(codes[1][-5:]) == int(codes[0][-5:]) + 1

    async def test_tasks_without_a_deadline_do_not_hide_the_burning_ones(
        self, assistant_api: AsyncClient
    ) -> None:
        """Задача без срока не должна вставать впереди горящей ни в одном направлении."""
        soon = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        await assistant_api.post("/api/v1/tasks", json=body(title="Без срока"))
        await assistant_api.post("/api/v1/tasks", json=body(title="Со сроком", due_at=soon))

        ascending = (await assistant_api.get("/api/v1/tasks", params={"sort_by": "due_at"})).json()
        descending = (
            await assistant_api.get(
                "/api/v1/tasks", params={"sort_by": "due_at", "descending": True}
            )
        ).json()

        assert ascending[0]["title"] == "Со сроком"
        assert descending[0]["title"] == "Со сроком"

    async def test_filters_narrow_the_base(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        person = Person(full_name="Исполнитель Один")
        session.add(person)
        await session.flush()

        await assistant_api.post(
            "/api/v1/tasks",
            json=body(
                title="Поручение",
                is_control=True,
                priority_code=Priority.URGENT.value,
                project_id=str(project.id),
                assignee_person_id=str(person.id),
            ),
        )
        await assistant_api.post("/api/v1/tasks", json=body(title="Обычная задача"))

        async def titles(**params: Any) -> list[str]:
            response = await assistant_api.get("/api/v1/tasks", params=params)
            return [item["title"] for item in response.json()]

        assert await titles(is_control=True) == ["Поручение"]
        assert await titles(priority_code=Priority.URGENT.value) == ["Поручение"]
        assert await titles(project_id=str(project.id)) == ["Поручение"]
        assert await titles(assignee_person_id=str(person.id)) == ["Поручение"]
        assert await titles(direction_id=str(project.direction_id)) == ["Поручение"]
        # Обе задачи без срока: при сортировке по сроку их порядок между собой не
        # определён, и требовать его от базы значило бы проверять случайность.
        assert sorted(await titles(status=TaskStatus.NEW.value)) == [
            "Обычная задача",
            "Поручение",
        ]
        assert await titles(search="обычн") == ["Обычная задача"]


class TestSingleTask:
    async def test_a_task_opens_by_its_identifier_with_the_computed_fields(
        self, assistant_api: AsyncClient
    ) -> None:
        past = (datetime.now(UTC) - timedelta(days=4)).isoformat()
        created = await assistant_api.post("/api/v1/tasks", json=body(due_at=past))

        card = await assistant_api.get(f"/api/v1/tasks/{created.json()['id']}")

        assert card.status_code == 200
        assert card.json()["is_overdue"] is True
        assert card.json()["days_overdue"] == 4

    async def test_a_missing_task_is_not_found_rather_than_forbidden(
        self, assistant_api: AsyncClient
    ) -> None:
        """404, а не 403: сообщение о запрете подтверждало бы, что запись существует."""
        response = await assistant_api.get(f"/api/v1/tasks/{uuid.uuid4()}")

        assert response.status_code == 404

    async def test_the_deadline_filter_narrows_by_date(self, assistant_api: AsyncClient) -> None:
        """«Что горит на этой неделе» — вопрос помощника каждое утро."""
        soon = datetime.now(UTC) + timedelta(days=2)
        later = datetime.now(UTC) + timedelta(days=20)
        await assistant_api.post(
            "/api/v1/tasks", json=body(title="На неделе", due_at=soon.isoformat())
        )
        await assistant_api.post(
            "/api/v1/tasks", json=body(title="Потом", due_at=later.isoformat())
        )

        response = await assistant_api.get(
            "/api/v1/tasks",
            params={"due_before": (datetime.now(UTC) + timedelta(days=7)).isoformat()},
        )

        assert [item["title"] for item in response.json()] == ["На неделе"]


class TestEveryChangeIsInTheJournal:
    async def test_creation_and_status_change_leave_a_trail(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        created = await assistant_api.post("/api/v1/tasks", json=body())
        task_id = uuid.UUID(created.json()["id"])

        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.IN_PROGRESS.value}
        )

        entries = list(
            await session.scalars(
                select(AuditLog).where(AuditLog.entity_id == task_id).order_by(AuditLog.occurred_at)
            )
        )
        assert [entry.action for entry in entries] == ["created", "updated"]
        assert entries[0].entity_type == "tasks"
        assert entries[1].changes["status"]["to"] == TaskStatus.IN_PROGRESS.value
        assert "started_at" in entries[1].changes, "отметка времени тоже изменение"


class TestControlFlag:
    async def test_a_control_task_is_marked_and_still_closable_for_now(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Признак заведён, запрет на закрытие — нет, и это осознанно.

        После запуска обмена ход исполнения поручения будет принадлежать SETA
        (ADR-0015), но запрет вводит ORB-076 — вместе с обменом. Ввести его сейчас
        значит сделать поручения незакрываемыми: закрывать их станет некому.
        """
        created = await assistant_api.post("/api/v1/tasks", json=body(is_control=True))
        task_id = created.json()["id"]
        assert created.json()["is_control"] is True

        await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.IN_PROGRESS.value}
        )
        closed = await assistant_api.patch(
            f"/api/v1/tasks/{task_id}", json={"status": TaskStatus.DONE.value}
        )

        assert closed.status_code == 200

        stored = await session.get(Task, uuid.UUID(task_id))
        assert stored is not None and stored.is_control is True
