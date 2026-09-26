"""API раздела «Проекты» — обещания экрана, утверждённого заказчиком 25.09.2026.

1. **Одни числа с Пультом** (инвариант 2, критерий 4 блока 1): ступень и отклонение
   проекта — те же строки лестницы, готовность и отставание — из сервиса показателей.
2. **Новый проект за два поля**: название и тип, вехи из шаблона (критерий 1).
3. **«Что если» не пишет в базу ничего**, пока не нажато «применить» (критерий 3).
4. **Правка по устаревшей версии — честный отказ**, а не молчаливая перезапись
   (инвариант 15).
5. Смотрят оба, вносит помощник.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import Attention
from app.domain.clock import local_date, now_utc
from app.domain.dictionaries import OrganizationKind, OrganizationRole, ProjectStatus, TaskStatus
from app.repos.models import (
    AuditLog,
    LeaderDecision,
    LeaderQuestion,
    Organization,
    Project,
    ProjectOrganization,
    ProjectTypeMilestone,
    ProjectTypeRef,
)
from app.services import metrics
from app.services.codes import add_with_code
from tests.factories import make_milestone, make_person, make_project, make_task

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")
PROJECTS = "/api/v1/projects"


def today() -> date:
    return local_date(now_utc(), TASHKENT)


def on(days: int) -> date:
    return today() + timedelta(days=days)


def card_of(body: dict[str, Any], project: Project) -> dict[str, Any]:
    found: list[dict[str, Any]] = [item for item in body["items"] if item["id"] == str(project.id)]
    assert found, f"проекта {project.title} нет в ответе"
    return found[0]


async def center(session: AsyncSession) -> Organization:
    found = await session.scalar(select(Organization).where(Organization.is_founded_by_agency))
    assert found is not None, "в сидах нет Центра"
    return found


async def partner(session: AsyncSession) -> Organization:
    organization = Organization(
        name=f"Министерство для проверки {now_utc().timestamp()}",
        kind=OrganizationKind.MINISTRY.value,
    )
    session.add(organization)
    await session.flush()
    return organization


async def audit_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(AuditLog)) or 0


class TestReading:
    async def test_steps_are_the_pult_steps(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Критерий 4: ступень проекта в разделе — та же строка, что на Пульте."""
        overdue = await make_project(session, due_on=on(-2))
        burning = await make_project(session, due_on=on(3))
        calm = await make_project(session, due_on=on(200))

        projects = (await leader_api.get(PROJECTS)).json()
        pult = (await leader_api.get("/api/v1/pult")).json()

        on_pult = {
            row["entity_id"]: (row["step"], row["deviation"])
            for row in pult["rows"]
            if row["section"] == "projects"
        }
        for item in projects["items"]:
            if item["step"] is None:
                assert item["id"] not in on_pult
            else:
                assert on_pult[item["id"]] == (item["step"], item["deviation"])

        assert card_of(projects, overdue)["step"] == "overdue"
        assert card_of(projects, overdue)["deviation"] == 2
        assert card_of(projects, burning)["step"] == "burning"
        assert card_of(projects, calm)["step"] is None

    async def test_order_is_ladder_then_plan_then_closed(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        closed = await make_project(session, due_on=on(-30), status=ProjectStatus.DONE)
        later = await make_project(session, due_on=on(300))
        sooner = await make_project(session, due_on=on(100))
        overdue = await make_project(session, due_on=on(-1))

        ids = [item["id"] for item in (await leader_api.get(PROJECTS)).json()["items"]]
        position = {
            str(project.id): ids.index(str(project.id))
            for project in (closed, later, sooner, overdue)
        }

        assert position[str(overdue.id)] < position[str(sooner.id)] < position[str(later.id)]
        assert position[str(later.id)] < position[str(closed.id)]

    async def test_readiness_and_lag_come_from_metrics(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(30))
        passed = await make_milestone(session, project=project, due_on=on(-10))
        passed.is_passed = True
        passed.passed_on = on(-10)
        await make_milestone(session, project=project, due_on=on(20))
        done = await make_task(session, due_at=None, project=project)
        done.status = TaskStatus.DONE.value
        await make_task(session, due_at=None, project=project)
        # Отменённая задача не входит в счёт: её не сделают.
        cancelled = await make_task(session, due_at=None, project=project)
        cancelled.status = TaskStatus.CANCELLED.value
        await session.flush()

        card = card_of((await leader_api.get(PROJECTS)).json(), project)
        expected = metrics.progress(
            status=ProjectStatus.IN_PROGRESS,
            started_on=project.started_on,
            due_on=project.due_on,
            today=today(),
            passed_milestones=1,
            total_milestones=2,
            done_tasks=1,
            total_tasks=2,
        )
        assert card["readiness"] == expected.readiness == 50
        assert card["lag_days"] == expected.lag_days
        assert card["milestones"] == {"passed": 1, "total": 2}
        assert card["tasks"] == {"done": 1, "total": 2}
        assert card["next_milestone"]["due_on"] == on(20).isoformat()
        assert [mark["is_passed"] for mark in card["marks"]] == [True, False]

    async def test_done_project_is_ready_and_not_lagging(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(-5), status=ProjectStatus.DONE)
        await make_milestone(session, project=project, due_on=on(-20))

        card = card_of((await leader_api.get(PROJECTS)).json(), project)
        assert card["readiness"] == 100
        assert card["lag_days"] == 0
        assert card["step"] is None

    async def test_impediment_goes_stale_by_threshold(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        fresh = await make_project(session, due_on=on(90))
        fresh.impediment = "Ждём заключение Минюста"
        fresh.impediment_updated_at = now_utc() - timedelta(days=3)
        old = await make_project(session, due_on=on(90))
        old.impediment = "Поставщик молчит"
        old.impediment_updated_at = now_utc() - timedelta(days=40)
        await session.flush()

        body = (await leader_api.get(PROJECTS)).json()
        assert card_of(body, fresh)["impediment"]["stale"] is False
        assert card_of(body, old)["impediment"]["stale"] is True
        assert (
            card_of(body, old)["impediment"]["updated_on"]
            == local_date(old.impediment_updated_at, TASHKENT).isoformat()
        )

    async def test_center_role_and_outside_lead(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        ours = await make_project(session, due_on=on(90))
        theirs = await make_project(session, due_on=on(90))
        session.add_all(
            [
                ProjectOrganization(
                    project_id=ours.id,
                    organization_id=(await center(session)).id,
                    role=OrganizationRole.EXECUTOR.value,
                ),
                ProjectOrganization(
                    project_id=theirs.id,
                    organization_id=(await partner(session)).id,
                    role=OrganizationRole.LEAD_AGENCY.value,
                ),
            ]
        )
        await session.flush()

        body = (await leader_api.get(PROJECTS)).json()
        assert card_of(body, ours)["center_role"] == "executor"
        assert card_of(body, ours)["lead_outside"] is False
        assert card_of(body, theirs)["center_role"] is None
        assert card_of(body, theirs)["lead_outside"] is True

    async def test_moves_are_later_shifts_from_the_journal(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Переносов два: подтянутый срок переносом не считается — как на Пульте."""
        project = await make_project(session, due_on=on(30))
        for days in (40, 35, 50):
            project.due_on = on(days)
            await session.flush()

        card = card_of((await leader_api.get(PROJECTS)).json(), project)
        assert card["moves"] == 2
        assert card["original_due_on"] == on(30).isoformat()
        assert card["due_on"] == on(50).isoformat()

    async def test_types_people_and_demo_mark(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        person = await make_person(session, "Проверочный А.")
        body = (await leader_api.get(PROJECTS)).json()

        assert body["is_demo"] is True
        assert {"id": str(person.id), "name": "Проверочный А."} in body["people"]
        regulation = next(kind for kind in body["types"] if kind["code"] == "regulation")
        assert regulation["name"]
        assert regulation["template"], "у нормативного акта должен быть шаблон вех"
        offsets = [step["offset_days"] for step in regulation["template"]]
        assert offsets == sorted(offsets)

    async def test_requires_a_session(self, api: AsyncClient) -> None:
        assert (await api.get(PROJECTS)).status_code == 401


class TestDetail:
    async def test_card_has_everything_the_sheet_shows(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_project(session, due_on=on(400), title="Программа")
        program.is_multiyear = True
        sub = await make_project(session, due_on=on(-3), title="Подпроект")
        sub.parent_project_id = program.id
        burning = await make_milestone(session, project=program, due_on=on(2), title="Горит")
        await make_task(session, due_at=None, project=program, title="Задача программы")
        session.add(
            ProjectOrganization(
                project_id=program.id,
                organization_id=(await center(session)).id,
                role=OrganizationRole.CO_EXECUTOR.value,
            )
        )
        session.add(
            LeaderQuestion(target_type="project", target_id=program.id, text="Утвердить план?")
        )
        await session.flush()

        response = await leader_api.get(f"{PROJECTS}/{program.id}")
        assert response.status_code == 200
        body = response.json()

        assert body["step"] == "awaiting_decision"
        assert body["question"]["text"] == "Утвердить план?"
        assert body["organizations"][0]["is_center"] is True
        assert body["organizations"][0]["role"] == "co_executor"
        mark = next(row for row in body["milestone_list"] if row["id"] == str(burning.id))
        assert mark["step"] == "burning"
        assert mark["deviation"] == 2
        assert mark["version"] == burning.version
        assert [row["title"] for row in body["subproject_list"]] == ["Подпроект"]
        assert body["subproject_list"][0]["step"] == "overdue"
        assert body["subprojects"] == 1
        assert [task["title"] for task in body["task_list"]] == ["Задача программы"]

    async def test_last_decision(self, leader_api: AsyncClient, session: AsyncSession) -> None:
        project = await make_project(session, due_on=on(60))
        session.add(
            LeaderDecision(
                target_type="project",
                target_id=project.id,
                kind="hurry",
                state="open",
            )
        )
        await session.flush()

        body = (await leader_api.get(f"{PROJECTS}/{project.id}")).json()
        assert body["last_decision"]["kind"] == "hurry"

    async def test_unknown_project(self, leader_api: AsyncClient) -> None:
        response = await leader_api.get(f"{PROJECTS}/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreate:
    async def test_two_fields_and_a_template(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Критерий 1: название и тип — остальное подставлено, вехи из шаблона."""
        kind = await session.scalar(
            select(ProjectTypeRef).where(ProjectTypeRef.code == "regulation")
        )
        assert kind is not None
        template = list(
            await session.scalars(
                select(ProjectTypeMilestone)
                .where(ProjectTypeMilestone.project_type_id == kind.id)
                .order_by(ProjectTypeMilestone.sort_order)
            )
        )
        started = on(0)

        response = await assistant_api.post(
            PROJECTS,
            json={
                "title": "  Положение о спутниковых данных  ",
                "type_code": "regulation",
                "started_on": started.isoformat(),
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()

        assert body["title"] == "Положение о спутниковых данных"
        assert body["code"].startswith(f"PRJ-{started.year}-")
        assert body["status"] == "in_progress"
        last = max(step.offset_days for step in template)
        assert body["due_on"] == (started + timedelta(days=last)).isoformat()
        assert body["original_due_on"] == body["due_on"]
        assert [row["title"] for row in body["milestone_list"]] == [
            step.name_ru for step in template
        ]
        assert (
            body["milestone_list"][0]["due_on"]
            == (started + timedelta(days=template[0].offset_days)).isoformat()
        )

        created = await session.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "projects", AuditLog.entity_id == body["id"]
            )
        )
        assert created is not None and created.action == "created"

    async def test_codes_follow_each_other(self, assistant_api: AsyncClient) -> None:
        payload = {"title": "Первый", "type_code": "standard", "started_on": on(0).isoformat()}
        first = (await assistant_api.post(PROJECTS, json=payload)).json()["code"]
        second = (await assistant_api.post(PROJECTS, json={**payload, "title": "Второй"})).json()[
            "code"
        ]
        assert int(second.rsplit("-", 1)[1]) == int(first.rsplit("-", 1)[1]) + 1

    async def test_subproject_of_a_program(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_project(session, due_on=on(700))
        program.is_multiyear = True
        person = await make_person(session)
        await session.flush()

        response = await assistant_api.post(
            PROJECTS,
            json={
                "title": "Калибровка",
                "type_code": "industry_pilot",
                "started_on": on(0).isoformat(),
                "due_on": on(90).isoformat(),
                "responsible_id": str(person.id),
                "parent_id": str(program.id),
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["parent"] == {"id": str(program.id), "title": program.title}
        assert body["responsible"]["id"] == str(person.id)
        assert body["due_on"] == on(90).isoformat()

    @pytest.mark.parametrize(
        ("patch", "status_code"),
        [
            ({"title": "   "}, 422),
            ({"type_code": "no_such_type"}, 422),
            ({"due_on": "2000-01-01"}, 422),
            ({"responsible_id": "00000000-0000-0000-0000-000000000000"}, 404),
            ({"parent_id": "00000000-0000-0000-0000-000000000000"}, 404),
        ],
    )
    async def test_refusals(
        self, assistant_api: AsyncClient, patch: dict[str, str], status_code: int
    ) -> None:
        payload = {"title": "Проект", "type_code": "standard", "started_on": on(0).isoformat()}
        response = await assistant_api.post(PROJECTS, json={**payload, **patch})
        assert response.status_code == status_code, response.text

    async def test_short_due_compresses_template(self, assistant_api: AsyncClient) -> None:
        """Срок раньше последней вехи шаблона: ни одна веха не позже срока проекта."""
        due = on(20)
        body = (
            await assistant_api.post(
                PROJECTS,
                json={
                    "title": "Срочное постановление",
                    "type_code": "regulation",
                    "started_on": on(0).isoformat(),
                    "due_on": due.isoformat(),
                },
            )
        ).json()
        dates = [row["due_on"] for row in body["milestone_list"]]
        assert dates == sorted(dates)
        assert dates[-1] == due.isoformat()

    @pytest.mark.parametrize(
        "patch",
        [
            {"started_on": "9999-12-01"},
            {"due_on": "9999-12-01"},
            {"title": "Проект" + chr(0)},
        ],
    )
    async def test_refused_in_words_not_500(
        self, assistant_api: AsyncClient, patch: dict[str, str]
    ) -> None:
        payload = {"title": "Проект", "type_code": "standard", "started_on": on(0).isoformat()}
        response = await assistant_api.post(PROJECTS, json={**payload, **patch})
        assert response.status_code == 422, response.text

    async def test_parent_must_be_a_program(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        plain = await make_project(session, due_on=on(90))
        program = await make_project(session, due_on=on(700))
        program.is_multiyear = True
        await session.flush()
        payload = {"title": "Подпроект", "type_code": "standard", "started_on": on(0).isoformat()}

        not_program = await assistant_api.post(
            PROJECTS, json={**payload, "parent_id": str(plain.id)}
        )
        assert not_program.status_code == 422
        nested_program = await assistant_api.post(
            PROJECTS, json={**payload, "parent_id": str(program.id), "is_multiyear": True}
        )
        assert nested_program.status_code == 422

    async def test_code_collision_leaves_one_journal_entry(self, session: AsyncSession) -> None:
        """Занятый номер и повтор: в журнале одна запись «создан», с тем номером, что лёг."""
        existing = await make_project(session, due_on=on(30))
        codes = iter([existing.code, "PRJ-T-RETRY"])

        async def assign() -> str:
            return next(codes)

        project = Project(
            title="Повтор номера",
            project_type_id=existing.project_type_id,
            started_on=on(0),
            due_on=on(30),
            original_due_on=on(30),
            status_code=ProjectStatus.IN_PROGRESS.value,
        )
        await add_with_code(session, project, assign=assign)

        created = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_type == "projects",
                    AuditLog.entity_id == project.id,
                    AuditLog.action == "created",
                )
            )
        )
        assert project.code == "PRJ-T-RETRY"
        assert len(created) == 1
        assert created[0].changes["code"]["to"] == "PRJ-T-RETRY"

    async def test_leader_does_not_enter_data(self, leader_api: AsyncClient) -> None:
        response = await leader_api.post(
            PROJECTS,
            json={"title": "Проект", "type_code": "standard", "started_on": on(0).isoformat()},
        )
        assert response.status_code == 403


class TestStatus:
    async def test_pause_needs_a_reason(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(60))
        url = f"{PROJECTS}/{project.id}/status"

        refused = await assistant_api.put(
            url, json={"status": "on_hold", "reason": "  ", "version": project.version}
        )
        assert refused.status_code == 422

        paused = await assistant_api.put(
            url,
            json={"status": "on_hold", "reason": "Ждём финансирование", "version": project.version},
        )
        assert paused.status_code == 204, paused.text
        await session.refresh(project)
        assert project.status_code == "on_hold"
        assert project.status_reason == "Ждём финансирование"

        resumed = await assistant_api.put(
            url, json={"status": "in_progress", "reason": None, "version": project.version}
        )
        assert resumed.status_code == 204
        await session.refresh(project)
        assert project.status_reason is None

    async def test_stale_version_is_refused(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(60))
        seen = project.version
        project.title = "Переименован в соседней вкладке"
        await session.flush()

        response = await assistant_api.put(
            f"{PROJECTS}/{project.id}/status",
            json={"status": "done", "reason": None, "version": seen},
        )
        assert response.status_code == 409
        assert response.json()["type"].endswith("stale-data")
        await session.refresh(project)
        assert project.status_code == "in_progress"

    async def test_unknown_status(self, assistant_api: AsyncClient, session: AsyncSession) -> None:
        project = await make_project(session, due_on=on(60))
        response = await assistant_api.put(
            f"{PROJECTS}/{project.id}/status",
            json={"status": "overdue", "version": project.version},
        )
        assert response.status_code == 422

    async def test_leader_cannot(self, leader_api: AsyncClient, session: AsyncSession) -> None:
        project = await make_project(session, due_on=on(60))
        response = await leader_api.put(
            f"{PROJECTS}/{project.id}/status",
            json={"status": "done", "version": project.version},
        )
        assert response.status_code == 403


class TestImpediment:
    async def test_set_confirm_and_clear(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(60))
        url = f"{PROJECTS}/{project.id}/impediment"

        response = await assistant_api.put(
            url, json={"text": "  Ждём письмо Минфина  ", "version": project.version}
        )
        assert response.status_code == 204, response.text
        await session.refresh(project)
        assert project.impediment == "Ждём письмо Минфина"
        assert project.impediment_updated_at is not None
        assert now_utc() - project.impediment_updated_at < timedelta(minutes=1)

        cleared = await assistant_api.put(url, json={"text": "", "version": project.version})
        assert cleared.status_code == 204
        await session.refresh(project)
        assert project.impediment is None
        assert project.impediment_updated_at is None

    async def test_nul_is_refused(self, assistant_api: AsyncClient, session: AsyncSession) -> None:
        project = await make_project(session, due_on=on(60))
        response = await assistant_api.put(
            f"{PROJECTS}/{project.id}/impediment",
            json={"text": "Ждём" + chr(0), "version": project.version},
        )
        assert response.status_code == 422

    async def test_too_long(self, assistant_api: AsyncClient, session: AsyncSession) -> None:
        project = await make_project(session, due_on=on(60))
        response = await assistant_api.put(
            f"{PROJECTS}/{project.id}/impediment",
            json={"text": "я" * 501, "version": project.version},
        )
        assert response.status_code == 422


class TestWhatIf:
    async def test_writes_nothing(self, leader_api: AsyncClient, session: AsyncSession) -> None:
        """Критерий 3: расчёт показывает влияние и не меняет базу."""
        project = await make_project(session, due_on=on(60))
        mark = await make_milestone(session, project=project, due_on=on(30))
        journal = await audit_count(session)
        versions = (project.version, mark.version)

        response = await leader_api.post(
            f"{PROJECTS}/{project.id}/what-if",
            json={
                "changes": [{"kind": "milestone", "id": str(mark.id), "due_on": on(3).isoformat()}]
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()

        shift = next(row for row in body["milestones"] if row["id"] == str(mark.id))
        assert shift == {
            "id": str(mark.id),
            "title": mark.title,
            "before": None,
            "after": "burning",
        }
        assert body["pult"]["after"]["burning"] == body["pult"]["before"]["burning"] + 1

        await session.refresh(project)
        await session.refresh(mark)
        assert await audit_count(session) == journal
        assert (project.version, mark.version) == versions
        assert mark.due_on == on(30)

    async def test_numbers_are_the_metrics_numbers(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(60))
        body = (
            await assistant_api.post(
                f"{PROJECTS}/{project.id}/what-if",
                json={
                    "changes": [
                        {"kind": "project", "id": str(project.id), "due_on": on(-1).isoformat()}
                    ]
                },
            )
        ).json()

        before, after = await metrics.what_if(
            session,
            today=today(),
            zone=TASHKENT,
            changes={("projects", project.id): on(-1)},
        )
        for step in ("overdue", "burning", "awaiting_decision"):
            assert body["pult"]["before"][step] == before.count(Attention(step))
            assert body["pult"]["after"][step] == after.count(Attention(step))
        assert body["project"]["before"]["step"] is None
        # Отставание «после» — та же функция сервиса показателей с новым сроком.
        lag_after = metrics.progress(
            status=ProjectStatus.IN_PROGRESS,
            started_on=project.started_on,
            due_on=on(-1),
            today=today(),
            passed_milestones=0,
            total_milestones=0,
            done_tasks=0,
            total_tasks=0,
        ).lag_days
        assert body["project"]["after"] == {
            "step": "overdue",
            "deviation": 1,
            "lag_days": lag_after,
            "due_on": on(-1).isoformat(),
        }

    async def test_far_date_is_refused(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(60))
        response = await assistant_api.post(
            f"{PROJECTS}/{project.id}/what-if",
            json={"changes": [{"kind": "project", "id": str(project.id), "due_on": "9999-12-31"}]},
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("case", ["empty", "passed", "foreign", "closed", "twice"])
    async def test_refusals(
        self, assistant_api: AsyncClient, session: AsyncSession, case: str
    ) -> None:
        project = await make_project(
            session,
            due_on=on(60),
            status=ProjectStatus.DONE if case == "closed" else ProjectStatus.IN_PROGRESS,
        )
        mark = await make_milestone(session, project=project, due_on=on(30))
        other = await make_milestone(
            session, project=await make_project(session, due_on=on(60)), due_on=on(30)
        )
        if case == "passed":
            mark.is_passed = True
            mark.passed_on = on(-1)
            await session.flush()

        move = {"kind": "milestone", "id": str(mark.id), "due_on": on(10).isoformat()}
        changes = {
            "empty": [],
            "passed": [move],
            "foreign": [{**move, "id": str(other.id)}],
            "closed": [move],
            "twice": [move, move],
        }[case]
        response = await assistant_api.post(
            f"{PROJECTS}/{project.id}/what-if", json={"changes": changes}
        )
        assert response.status_code == (404 if case == "foreign" else 422), response.text


class TestApplyDates:
    async def test_writes_and_counts_a_move(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(60))
        mark = await make_milestone(session, project=project, due_on=on(30))

        response = await assistant_api.put(
            f"{PROJECTS}/{project.id}/dates",
            json={
                "changes": [
                    {
                        "kind": "project",
                        "id": str(project.id),
                        "due_on": on(90).isoformat(),
                        "version": project.version,
                    },
                    {
                        "kind": "milestone",
                        "id": str(mark.id),
                        "due_on": on(45).isoformat(),
                        "version": mark.version,
                    },
                ]
            },
        )
        assert response.status_code == 204, response.text

        await session.refresh(project)
        await session.refresh(mark)
        assert (project.due_on, project.original_due_on) == (on(90), on(60))
        assert (mark.due_on, mark.original_due_on) == (on(45), on(30))

        card = card_of((await assistant_api.get(PROJECTS)).json(), project)
        assert card["moves"] == 1

    async def test_stale_milestone_version_changes_nothing(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(60))
        mark = await make_milestone(session, project=project, due_on=on(30))
        seen = mark.version
        mark.title = "Переименована в соседней вкладке"
        await session.flush()

        response = await assistant_api.put(
            f"{PROJECTS}/{project.id}/dates",
            json={
                "changes": [
                    {
                        "kind": "project",
                        "id": str(project.id),
                        "due_on": on(90).isoformat(),
                        "version": project.version,
                    },
                    {
                        "kind": "milestone",
                        "id": str(mark.id),
                        "due_on": on(45).isoformat(),
                        "version": seen,
                    },
                ]
            },
        )
        assert response.status_code == 409
        await session.refresh(project)
        assert project.due_on == on(60), "отказ откатывает и срок проекта"

    async def test_leader_cannot(self, leader_api: AsyncClient, session: AsyncSession) -> None:
        project = await make_project(session, due_on=on(60))
        response = await leader_api.put(
            f"{PROJECTS}/{project.id}/dates",
            json={
                "changes": [
                    {
                        "kind": "project",
                        "id": str(project.id),
                        "due_on": on(90).isoformat(),
                        "version": project.version,
                    }
                ]
            },
        )
        assert response.status_code == 403
