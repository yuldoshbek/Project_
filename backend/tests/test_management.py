"""API Управления — обещания экрана, утверждённого заказчиком 29.09.2026.

1. **Обход** (ТЗ 7, V20): очередь из данных — решение, задача и веха со сроком в прошлом,
   задача на проверке и молчащий проект дольше порога, устаревшее «что мешает», задача без
   ответственного; одна запись — один раз; действие меняет данные и засчитывается неделе.
2. **Пороги** (ТЗ 4): «сейчас» — те же числа, что у Пульта и Календаря; предпросмотр ничего
   не пишет; запись — в границах, по версии и в журнал — и меняет сигналы.
3. **Справочники** (ТЗ 3.9): переименовать, выключить, порядок, добавить; статусы не
   выключаются; организации — по названию; шаблон вех — по сроку от начала.
4. **Доступ** (ТЗ 3.8): дата выпуска и последний вход, и после перевыпуска.
5. Смотрят оба одной формой; правит помощник.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import local_date, now_utc
from app.domain.decisions import DecisionKind, DecisionState
from app.domain.dictionaries import OrganizationKind, OrganizationRole, ProjectStatus, TaskStatus
from app.repos.models import (
    AuditLog,
    LeaderDecision,
    Milestone,
    Organization,
    Project,
    ProjectOrganization,
    ProjectTypeRef,
    RoundMark,
    Session,
    Setting,
    Task,
    TaskTypeRef,
    User,
)
from app.services import access
from tests.factories import make_milestone, make_person, make_project, make_task

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")
MANAGEMENT = "/api/v1/management"
ROUND = f"{MANAGEMENT}/round"


def today() -> date:
    return local_date(now_utc(), TASHKENT)


def on(days: int) -> date:
    return today() + timedelta(days=days)


def at(day: date, hour: int = 18) -> datetime:
    return datetime.combine(day, time(hour), TASHKENT).astimezone(UTC)


async def view(api: AsyncClient) -> dict[str, Any]:
    response = await api.get(MANAGEMENT)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def items(body: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = body["round"]["items"]
    return found


def item_of(body: dict[str, Any], record_id: object) -> dict[str, Any]:
    found = [each for each in items(body) if each["record"]["id"] == str(record_id)]
    assert found, f"записи {record_id} нет в обходе"
    return found[0]


def in_round(body: dict[str, Any], record_id: object) -> bool:
    return any(each["record"]["id"] == str(record_id) for each in items(body))


async def backdate(session: AsyncSession, model: Any, record_id: uuid.UUID, days: int) -> None:
    """Запись заведена давно и с тех пор не правилась — мимо ORM, чтобы не поднять версию."""
    moment = now_utc() - timedelta(days=days)
    await session.execute(
        update(model).where(model.id == record_id).values(created_at=moment, updated_at=None)
    )
    await session.flush()


async def reviewed_task(session: AsyncSession, title: str, days: int) -> Task:
    """Задача, заведённая сразу на проверке: перехода в журнале нет, отсчёт — от создания.

    Ответственный есть: без него задача встала бы в обход по другой причине.
    """
    person = await make_person(session, "Проверяющий П.")
    task = Task(
        code=f"TSK-R-{uuid.uuid4().hex[:6]}",
        title=title,
        assignee_person_id=person.id,
        status=TaskStatus.IN_REVIEW.value,
        due_at=at(on(30)),
        original_due_at=at(on(30)),
    )
    session.add(task)
    await session.flush()
    await backdate(session, Task, task.id, days)
    return task


async def act(api: AsyncClient, item: dict[str, Any], action: str, text: str | None = None) -> Any:
    body: dict[str, Any] = {
        "reason": item["reason"],
        "record_kind": item["record"]["kind"],
        "record_id": item["record"]["id"],
        "action": action,
        "version": item["record"]["version"],
    }
    if text is not None:
        body["input"] = text
    return await api.post(ROUND, json=body)


async def threshold(api: AsyncClient, key: str) -> dict[str, Any]:
    found: list[dict[str, Any]] = [
        each for each in (await view(api))["thresholds"] if each["key"] == key
    ]
    assert found
    return found[0]


class TestRound:
    async def test_queue_from_data_with_reasons_targets_and_actions(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        person = await make_person(session, "Рахимов Ш.")
        project = await make_project(session, due_on=on(90), responsible=person, title="Засуха")
        late = await make_task(
            session, due_at=at(on(-3)), project=project, assignee=person, title="Справка"
        )
        fresh = await make_task(session, due_at=at(on(-1)), assignee=person, title="Новая")
        fresh.status = TaskStatus.NEW.value
        mark = await make_milestone(session, project=project, due_on=on(-9), title="Приёмка")
        decision = LeaderDecision(
            target_type="task",
            target_id=late.id,
            kind=DecisionKind.HURRY.value,
            text="Поторопить: справка",
            assignee_person_id=person.id,
            due_on=on(-2),
            state=DecisionState.OPEN.value,
        )
        session.add(decision)
        await session.flush()

        body = await view(leader_api)
        hurry = item_of(body, decision.id)
        assert (hurry["reason"], hurry["days"], hurry["target"]) == (
            "decision_overdue",
            2,
            {"kind": "task", "id": str(late.id)},
        )
        assert hurry["actions"] == ["decision_done", "move_week"]
        overdue = item_of(body, late.id)
        assert (overdue["reason"], overdue["days"], overdue["owner"], overdue["responsible"]) == (
            "task_overdue",
            3,
            "Засуха",
            "Рахимов Ш.",
        )
        assert overdue["actions"] == ["task_done", "move_week", "task_cancel"]
        # У новой задачи «сделана» нет: граф переходов не пускает «новая → готова».
        assert item_of(body, fresh.id)["actions"] == ["move_week", "task_cancel"]
        milestone = item_of(body, mark.id)
        assert (milestone["reason"], milestone["days"], milestone["target"]["kind"]) == (
            "milestone_passed",
            9,
            "project",
        )
        assert milestone["target"]["id"] == str(project.id)
        assert milestone["record"] == {"kind": "milestone", "id": str(mark.id), "version": 1}
        # Порядок очереди — порядок причин.
        reasons = [each["reason"] for each in items(body)]
        assert reasons.index("decision_overdue") < reasons.index("task_overdue")
        assert reasons.index("task_overdue") < reasons.index("milestone_passed")

    async def test_review_silence_impediment_and_unassigned_by_thresholds(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        reviewed = await reviewed_task(session, "Согласование", 16)
        recent_review = await reviewed_task(session, "Недавно на проверке", 5)

        silent = await make_project(session, due_on=on(90), title="Лаборатория")
        await backdate(session, Project, silent.id, 30)

        noted = await make_project(session, due_on=on(90), title="Программа воздуха")
        fresh_note = await make_project(session, due_on=on(90), title="Геопортал")
        for project, days in ((noted, 20), (fresh_note, 5)):
            await session.execute(
                update(Project)
                .where(Project.id == project.id)
                .values(impediment="Ждём ответ партнёра", impediment_updated_at=at(on(-days), 10))
            )

        orphan = await make_task(session, due_at=at(on(30)), title="Письмо без ответственного")
        today_orphan = await make_task(session, due_at=at(on(30)), title="Заведена сегодня")
        await backdate(session, Task, orphan.id, 6)

        body = await view(leader_api)
        assert item_of(body, reviewed.id)["reason"] == "task_review"
        assert item_of(body, reviewed.id)["actions"] == ["task_done", "task_back"]
        assert not in_round(body, recent_review.id)
        assert (item_of(body, silent.id)["reason"], item_of(body, silent.id)["days"]) == (
            "project_silent",
            30,
        )
        assert item_of(body, silent.id)["actions"] == ["note", "project_done", "hold"]
        assert (item_of(body, noted.id)["reason"], item_of(body, noted.id)["days"]) == (
            "impediment_stale",
            20,
        )
        assert not in_round(body, fresh_note.id)
        assert item_of(body, orphan.id)["reason"] == "task_unassigned"
        assert item_of(body, orphan.id)["responsible"] is None
        assert not in_round(body, today_orphan.id)

    async def test_one_record_once_by_the_first_reason(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Просроченная задача без ответственного — один пункт, «просрочена»."""
        task = await make_task(session, due_at=at(on(-4)), title="Ничья и просроченная")
        await backdate(session, Task, task.id, 10)
        body = await view(leader_api)
        assert [each["reason"] for each in items(body) if each["record"]["id"] == str(task.id)] == [
            "task_overdue"
        ]

    async def test_quiet_threshold_drives_the_round(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        silent = await make_project(session, due_on=on(90), title="Молчит 20 дней")
        await backdate(session, Project, silent.id, 20)
        assert in_round(await view(assistant_api), silent.id)

        quiet = await threshold(assistant_api, "quiet_days")
        saved = await assistant_api.put(
            f"{MANAGEMENT}/thresholds/quiet_days", json={"value": 25, "version": quiet["version"]}
        )
        assert saved.status_code == 204
        assert not in_round(await view(assistant_api), silent.id)


class TestRoundActions:
    async def test_decision_done_and_the_week_counts_it(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        task = await make_task(session, due_at=at(on(20)))
        decision = LeaderDecision(
            target_type="task",
            target_id=task.id,
            kind=DecisionKind.HURRY.value,
            due_on=on(-1),
            state=DecisionState.OPEN.value,
        )
        session.add(decision)
        await session.flush()
        before = await view(assistant_api)

        response = await act(assistant_api, item_of(before, decision.id), "decision_done")
        assert response.status_code == 204
        await session.refresh(decision)
        assert (decision.state, decision.done_on) == (DecisionState.DONE.value, today())
        after = await view(assistant_api)
        assert not in_round(after, decision.id)
        assert after["round"]["done"] == before["round"]["done"] + 1
        assert await session.scalar(select(func.count()).select_from(RoundMark)) == 1

    async def test_move_week_is_a_week_from_today(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(90))
        mark = await make_milestone(session, project=project, due_on=on(-9))
        task = await make_task(session, due_at=at(on(-3)), project=project)
        body = await view(assistant_api)

        assert (await act(assistant_api, item_of(body, mark.id), "move_week")).status_code == 204
        assert (await act(assistant_api, item_of(body, task.id), "move_week")).status_code == 204
        await session.refresh(mark)
        await session.refresh(task)
        assert mark.due_on == on(7)
        assert task.due_at is not None and local_date(task.due_at, TASHKENT) == on(7)
        after = await view(assistant_api)
        assert not in_round(after, mark.id) and not in_round(after, task.id)

    async def test_milestone_passed_and_task_back(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(90))
        mark = await make_milestone(session, project=project, due_on=on(-2))
        review = await reviewed_task(session, "На проверке давно", 20)
        body = await view(assistant_api)

        passed = await act(assistant_api, item_of(body, mark.id), "milestone_passed")
        assert passed.status_code == 204, passed.text
        assert (await act(assistant_api, item_of(body, review.id), "task_back")).status_code == 204
        await session.refresh(mark)
        await session.refresh(review)
        assert (mark.is_passed, mark.passed_on) == (True, today())
        assert review.status == TaskStatus.IN_PROGRESS.value

    async def test_impediment_confirm_clear_and_note(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        projects = [await make_project(session, due_on=on(90)) for _ in range(3)]
        for project in projects:
            await session.execute(
                update(Project)
                .where(Project.id == project.id)
                .values(impediment="Ждём ответ", impediment_updated_at=at(on(-20), 10))
            )
            await session.refresh(project)
        body = await view(assistant_api)
        confirm, clear, note = (item_of(body, project.id) for project in projects)

        confirmed = await act(assistant_api, confirm, "impediment_confirm")
        assert confirmed.status_code == 204, confirmed.text
        assert (await act(assistant_api, clear, "impediment_clear")).status_code == 204
        assert (await act(assistant_api, note, "note")).status_code == 422
        assert (await act(assistant_api, note, "note", "Партнёр сменил контакт")).status_code == 204

        rows = {
            row.id: row
            for row in await session.scalars(
                select(Project).where(Project.id.in_([project.id for project in projects]))
            )
        }
        for row in rows.values():
            await session.refresh(row)
        assert rows[projects[0].id].impediment == "Ждём ответ"
        assert rows[projects[1].id].impediment is None
        assert rows[projects[2].id].impediment == "Партнёр сменил контакт"
        after = await view(assistant_api)
        assert not any(in_round(after, project.id) for project in projects)

    async def test_hold_needs_a_reason_and_done_closes(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        paused = await make_project(session, due_on=on(90))
        finished = await make_project(session, due_on=on(90))
        for project in (paused, finished):
            await backdate(session, Project, project.id, 30)
        body = await view(assistant_api)

        assert (await act(assistant_api, item_of(body, paused.id), "hold")).status_code == 422
        response = await act(assistant_api, item_of(body, paused.id), "hold", "Ждём финансирование")
        assert response.status_code == 204
        assert (
            await act(assistant_api, item_of(body, finished.id), "project_done")
        ).status_code == 204
        await session.refresh(paused)
        await session.refresh(finished)
        assert (paused.status_code, paused.status_reason) == (
            ProjectStatus.ON_HOLD.value,
            "Ждём финансирование",
        )
        assert finished.status_code == ProjectStatus.DONE.value

    async def test_assign_from_the_people_list(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        karimov = await make_person(session, "Каримов А.")
        task = await make_task(session, due_at=at(on(30)))
        await backdate(session, Task, task.id, 5)
        body = await view(assistant_api)
        assert str(karimov.id) in [person["id"] for person in body["people"]]
        item = item_of(body, task.id)

        assert (await act(assistant_api, item, "assign", "не-идентификатор")).status_code == 422
        assert (await act(assistant_api, item, "assign", str(karimov.id))).status_code == 204
        await session.refresh(task)
        assert task.assignee_person_id == karimov.id

    async def test_refusals(
        self, assistant_api: AsyncClient, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        task = await make_task(session, due_at=at(on(-3)))
        body = await view(assistant_api)
        item = item_of(body, task.id)
        before = await session.scalar(select(func.count()).select_from(RoundMark))

        assert (await act(leader_api, item, "task_done")).status_code == 403
        assert (await act(assistant_api, item, "milestone_passed")).status_code == 422
        wrong_kind = {**item, "record": {**item["record"], "kind": "project"}}
        assert (await act(assistant_api, wrong_kind, "task_done")).status_code == 422
        stale = {**item, "record": {**item["record"], "version": item["record"]["version"] + 5}}
        assert (await act(assistant_api, stale, "task_done")).status_code == 409
        extra = await assistant_api.post(
            ROUND,
            json={
                "reason": item["reason"],
                "record_kind": "task",
                "record_id": item["record"]["id"],
                "action": "task_done",
                "version": item["record"]["version"],
                "comment": "лишнее",
            },
        )
        assert extra.status_code == 422
        assert await session.scalar(select(func.count()).select_from(RoundMark)) == before

    async def test_action_is_journaled_with_the_record(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        task = await make_task(session, due_at=at(on(-3)))
        body = await view(assistant_api)
        assert (await act(assistant_api, item_of(body, task.id), "task_cancel")).status_code == 204
        entries = list(
            await session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_type == "tasks", AuditLog.entity_id == task.id
                )
            )
        )
        assert any("status" in (entry.changes or {}) for entry in entries)


class TestThresholds:
    async def test_now_numbers_are_the_pult_and_calendar_numbers(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        for days in (1, 3, 6):
            await make_task(session, due_at=at(on(days)))
        silent = await make_project(session, due_on=on(90))
        await backdate(session, Project, silent.id, 30)

        body = await view(leader_api)
        pult = (await leader_api.get("/api/v1/pult")).json()
        calendar = (await leader_api.get(f"/api/v1/calendar?from={on(0)}&to={on(0)}")).json()
        by_key = {each["key"]: each for each in body["thresholds"]}
        assert list(by_key) == [
            "burn_days",
            "quiet_days",
            "impediment_stale_days",
            "min_closed_for_pace",
            "hot_day_threshold",
            "hot_window_days",
            "summary_at",
            "sleeping_days",
            "min_letters_for_speed",
        ]
        assert by_key["burn_days"]["affected"] == pult["counts"]["burning"]
        assert by_key["quiet_days"]["affected"] == (
            pult["counts"]["silent"] + pult["counts"]["blocked_by_others"]
        )
        assert by_key["hot_day_threshold"]["affected"] == len(calendar["hot_ahead"])
        assert by_key["hot_window_days"]["affected"] == len(calendar["hot_ahead"])
        assert by_key["summary_at"]["affected"] is None
        assert (by_key["burn_days"]["default"], by_key["burn_days"]["origin"]) == (7, "tz")
        assert by_key["hot_day_threshold"]["origin"] == "assumption"
        assert (by_key["burn_days"]["min"], by_key["burn_days"]["max"]) == (1, 60)
        # У времени сводки границы — её окно, строками: экран ставит их полю времени.
        assert (by_key["summary_at"]["min"], by_key["summary_at"]["max"]) == ("06:00", "11:00")

    async def test_quiet_counts_projects_waiting_for_outsiders(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Проект с чужим головным молчит той же тишиной: он и в обходе, и в числе порога."""
        theirs = await make_project(session, due_on=on(90), title="Ждёт министерство")
        ministry = Organization(
            name="Министерство для обхода", kind=OrganizationKind.MINISTRY.value
        )
        session.add(ministry)
        await session.flush()
        session.add(
            ProjectOrganization(
                project_id=theirs.id,
                organization_id=ministry.id,
                role=OrganizationRole.LEAD_AGENCY.value,
            )
        )
        await session.flush()
        await backdate(session, Project, theirs.id, 20)

        pult = (await leader_api.get("/api/v1/pult")).json()
        assert (pult["counts"]["silent"], pult["counts"]["blocked_by_others"]) == (0, 1)
        assert item_of(await view(leader_api), theirs.id)["reason"] == "project_silent"
        assert (await threshold(leader_api, "quiet_days"))["affected"] == 1
        later = await leader_api.get(f"{MANAGEMENT}/thresholds/quiet_days/preview?value=25")
        assert later.json()["affected"] == 0

    async def test_preview_writes_nothing(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        for days in (1, 10, 12):
            await make_task(session, due_at=at(on(days)))
        now = (await threshold(leader_api, "burn_days"))["affected"]
        wider = (await leader_api.get(f"{MANAGEMENT}/thresholds/burn_days/preview?value=14")).json()
        assert wider["affected"] == now + 2
        assert (await threshold(leader_api, "burn_days"))["affected"] == now
        stored = await session.scalar(select(Setting.value).where(Setting.key == "burn_days"))
        assert stored == 7

        for query, code in (
            ("burn_days/preview?value=61", 422),
            ("burn_days/preview?value=сколько", 422),
            ("no_such/preview?value=3", 404),
            ("summary_at/preview?value=25:00", 422),
        ):
            assert (await leader_api.get(f"{MANAGEMENT}/thresholds/{query}")).status_code == code
        summary = await leader_api.get(f"{MANAGEMENT}/thresholds/summary_at/preview?value=08:00")
        assert summary.json() == {"affected": None}

    async def test_save_changes_signals_by_version_and_journal(
        self, assistant_api: AsyncClient, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        await make_task(session, due_at=at(on(10)))
        burn = await threshold(assistant_api, "burn_days")
        path = f"{MANAGEMENT}/thresholds/burn_days"

        assert (
            await leader_api.put(path, json={"value": 12, "version": burn["version"]})
        ).status_code == 403
        assert (
            await assistant_api.put(path, json={"value": 0, "version": burn["version"]})
        ).status_code == 422
        assert (
            await assistant_api.put(path, json={"value": 12, "version": burn["version"]})
        ).status_code == 204

        after = await threshold(assistant_api, "burn_days")
        assert (after["value"], after["version"]) == (12, burn["version"] + 1)
        pult = (await assistant_api.get("/api/v1/pult")).json()
        assert after["affected"] == pult["counts"]["burning"]

        stale = await assistant_api.put(path, json={"value": 9, "version": burn["version"]})
        assert stale.status_code == 409
        assert "сейчас 12" in stale.json()["detail"]
        journal = await session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.entity_type == "settings")
        )
        assert journal and journal >= 1

    async def test_summary_time(self, assistant_api: AsyncClient) -> None:
        summary = await threshold(assistant_api, "summary_at")
        path = f"{MANAGEMENT}/thresholds/summary_at"
        assert (
            await assistant_api.put(path, json={"value": "8:30", "version": summary["version"]})
        ).status_code == 422
        assert (
            await assistant_api.put(path, json={"value": "11:30", "version": summary["version"]})
        ).status_code == 422
        assert (
            await assistant_api.put(path, json={"value": "09:00", "version": summary["version"]})
        ).status_code == 204
        assert (await threshold(assistant_api, "summary_at"))["value"] == "09:00"


class TestDictionaries:
    @staticmethod
    def group(body: dict[str, Any], kind: str) -> dict[str, Any]:
        found: list[dict[str, Any]] = [
            each for each in body["dictionaries"] if each["kind"] == kind
        ]
        assert found
        return found[0]

    @staticmethod
    def entry(group: dict[str, Any], name: str) -> dict[str, Any]:
        found: list[dict[str, Any]] = [each for each in group["entries"] if each["name"] == name]
        assert found, f"нет «{name}»"
        return found[0]

    async def test_groups_flags_and_usage(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        await make_project(session, due_on=on(90))
        body = await view(leader_api)
        kinds = [each["kind"] for each in body["dictionaries"]]
        assert kinds == [
            "project_types",
            "task_types",
            "directions",
            "regions",
            "project_statuses",
            "task_statuses",
            "organizations",
        ]
        flags = {
            each["kind"]: (each["can_add"], each["can_disable"], each["can_move"])
            for each in body["dictionaries"]
        }
        assert flags["task_statuses"] == (False, False, True)
        assert flags["regions"] == (False, True, True)
        assert flags["organizations"] == (True, True, False)
        statuses = self.group(body, "project_statuses")
        assert self.entry(statuses, "В работе")["used"] >= 1
        assert len(self.group(body, "regions")["entries"]) == 14

    async def test_rename_follows_uzbek_copies_and_refuses_duplicates(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        body = await view(assistant_api)
        other = self.entry(self.group(body, "task_types"), "Прочее")
        path = f"{MANAGEMENT}/dictionaries/task_types/{other['id']}"

        taken = await assistant_api.put(
            path, json={"name": "согласование", "version": other["version"]}
        )
        assert taken.status_code == 409
        renamed = await assistant_api.put(
            path, json={"name": "Прочее и разное", "version": other["version"]}
        )
        assert renamed.status_code == 204
        row = await session.get(TaskTypeRef, uuid.UUID(other["id"]))
        assert row is not None
        await session.refresh(row)
        assert (row.name_ru, row.version) == ("Прочее и разное", other["version"] + 1)
        stale = await assistant_api.put(path, json={"name": "Иное", "version": other["version"]})
        assert stale.status_code == 409

    async def test_toggle_move_and_add(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        body = await view(assistant_api)
        types = self.group(body, "task_types")
        upload = self.entry(types, "Выгрузка в субплатформу")
        toggled = await assistant_api.post(
            f"{MANAGEMENT}/dictionaries/task_types/{upload['id']}/toggle",
            json={"version": upload["version"]},
        )
        assert toggled.status_code == 204
        active = (await assistant_api.get("/api/v1/dictionaries")).json()["task_types"]
        assert "Выгрузка в субплатформу" not in [each["name"]["ru"] for each in active]

        names = [each["name"] for each in types["entries"]]
        approval = self.entry(types, "Согласование")
        moved = await assistant_api.post(
            f"{MANAGEMENT}/dictionaries/task_types/{approval['id']}/move",
            json={"step": -1, "version": approval["version"]},
        )
        assert moved.status_code == 204
        after = [
            each["name"] for each in self.group(await view(assistant_api), "task_types")["entries"]
        ]
        index = names.index("Согласование")
        assert after[index - 1] == "Согласование" and after[index] == names[index - 1]

        created = await assistant_api.post(
            f"{MANAGEMENT}/dictionaries/task_types", json={"name": "Подготовка презентации"}
        )
        assert created.status_code == 201
        fresh = self.entry(
            self.group(await view(assistant_api), "task_types"), "Подготовка презентации"
        )
        assert (fresh["used"], fresh["is_active"]) == (0, True)
        row = await session.get(TaskTypeRef, uuid.UUID(created.json()["id"]))
        assert row is not None and row.name_uz_latn == "Подготовка презентации"

    async def test_statuses_regions_and_organizations_rules(
        self, assistant_api: AsyncClient
    ) -> None:
        body = await view(assistant_api)
        status_entry = self.entry(self.group(body, "task_statuses"), "Новая")
        refused = await assistant_api.post(
            f"{MANAGEMENT}/dictionaries/task_statuses/{status_entry['id']}/toggle",
            json={"version": status_entry["version"]},
        )
        assert refused.status_code == 422
        region = await assistant_api.post(
            f"{MANAGEMENT}/dictionaries/regions", json={"name": "Новая область"}
        )
        assert region.status_code == 422

        created = await assistant_api.post(
            f"{MANAGEMENT}/dictionaries/organizations",
            json={"name": "Агентство по гидрометеорологии", "org_kind": "agency"},
        )
        assert created.status_code == 201
        organization = self.entry(
            self.group(await view(assistant_api), "organizations"), "Агентство по гидрометеорологии"
        )
        assert (organization["org_kind"], organization["is_center"]) == ("agency", False)
        moved = await assistant_api.post(
            f"{MANAGEMENT}/dictionaries/organizations/{organization['id']}/move",
            json={"step": 1, "version": organization["version"]},
        )
        assert moved.status_code == 422
        renamed = await assistant_api.put(
            f"{MANAGEMENT}/dictionaries/organizations/{organization['id']}",
            json={
                "name": "Агентство гидрометеорологии",
                "org_kind": "ministry",
                "version": organization["version"],
            },
        )
        assert renamed.status_code == 204
        after = self.entry(
            self.group(await view(assistant_api), "organizations"), "Агентство гидрометеорологии"
        )
        assert after["org_kind"] == "ministry"

    async def test_renamed_center_shows_under_new_name_on_projects(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Краткое название Центра из наполнения не перекрывает имя, данное в Управлении."""
        center = next(
            each
            for each in self.group(await view(assistant_api), "organizations")["entries"]
            if each["is_center"]
        )
        renamed = await assistant_api.put(
            f"{MANAGEMENT}/dictionaries/organizations/{center['id']}",
            json={"name": "Центр мониторинга и ГИС", "version": center["version"]},
        )
        assert renamed.status_code == 204

        project = await make_project(session, due_on=on(90))
        joined = await assistant_api.put(
            f"/api/v1/projects/{project.id}/organizations/{center['id']}",
            json={"role": "executor"},
        )
        assert joined.status_code == 204
        card = (await assistant_api.get(f"/api/v1/projects/{project.id}")).json()
        assert [each["name"] for each in card["organizations"]] == ["Центр мониторинга и ГИС"]
        catalog = (await assistant_api.get("/api/v1/organizations")).json()
        found = next(each for each in catalog if each["id"] == center["id"])
        assert (found["name"], found["short_name"]) == ("Центр мониторинга и ГИС", None)

    async def test_leader_reads_but_cannot_edit(self, leader_api: AsyncClient) -> None:
        body = await view(leader_api)
        other = self.entry(self.group(body, "task_types"), "Прочее")
        response = await leader_api.put(
            f"{MANAGEMENT}/dictionaries/task_types/{other['id']}",
            json={"name": "Иное", "version": other["version"]},
        )
        assert response.status_code == 403


class TestTemplates:
    async def test_steps_by_offset_and_new_project_follows(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        regulation = await session.scalar(
            select(ProjectTypeRef).where(ProjectTypeRef.code == "regulation")
        )
        assert regulation is not None
        path = f"{MANAGEMENT}/templates/{regulation.id}/steps"

        created = await assistant_api.post(path, json={"name": "Экспертиза", "offset_days": 45})
        assert created.status_code == 201
        steps = (await view(assistant_api))["templates"][str(regulation.id)]
        assert [step["offset_days"] for step in steps] == [30, 45, 60, 90, 120]

        # Новый проект этого типа получает веху по своему сроку, а не в конец.
        project = await assistant_api.post(
            "/api/v1/projects",
            json={
                "title": "Постановление о геоданных",
                "type_code": "regulation",
                "started_on": today().isoformat(),
                "due_on": on(200).isoformat(),
            },
        )
        assert project.status_code == 201, project.text
        marks = list(
            await session.scalars(
                select(Milestone)
                .where(Milestone.project_id == uuid.UUID(project.json()["id"]))
                .order_by(Milestone.sort_order)
            )
        )
        assert [mark.title for mark in marks][1] == "Экспертиза"

        step = next(step for step in steps if step["name"] == "Экспертиза")
        edited = await assistant_api.put(
            f"{path}/{step['id']}",
            json={"name": "Экспертиза проекта", "offset_days": 100, "version": step["version"]},
        )
        assert edited.status_code == 204
        stale = await assistant_api.delete(f"{path}/{step['id']}?version={step['version']}")
        assert stale.status_code == 409
        removed = await assistant_api.delete(f"{path}/{step['id']}?version={step['version'] + 1}")
        assert removed.status_code == 204
        assert [
            step["name"] for step in (await view(assistant_api))["templates"][str(regulation.id)]
        ] == [
            "Разработка проекта акта",
            "Согласование с министерствами и ведомствами",
            "Внесение в Кабинет Министров",
            "Принятие",
        ]

    async def test_offset_bounds_and_foreign_type(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        regulation = await session.scalar(
            select(ProjectTypeRef).where(ProjectTypeRef.code == "regulation")
        )
        assert regulation is not None
        path = f"{MANAGEMENT}/templates/{regulation.id}/steps"
        assert (
            await assistant_api.post(path, json={"name": "Веха", "offset_days": -1})
        ).status_code == 422
        assert (
            await assistant_api.post(path, json={"name": "Веха", "offset_days": 4000})
        ).status_code == 422
        missing = await assistant_api.post(
            f"{MANAGEMENT}/templates/{uuid.uuid4()}/steps", json={"name": "Веха", "offset_days": 5}
        )
        assert missing.status_code == 404


class TestAccess:
    async def test_issue_date_and_last_login_survive_reissue(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        # Смотрит помощник: перевыпуск ссылки руководителя гасит все сессии руководителя.
        leader = await session.scalar(select(User).where(User.role == "leader"))
        assert leader is not None
        moment = now_utc() - timedelta(days=3)
        issued = await access.issue_link(
            session, user=leader, secret="секрет-теста", base_url="https://test", now=moment
        )
        del issued
        seen = now_utc() - timedelta(days=2)
        session.add(
            Session(
                user_id=leader.id,
                token_fingerprint=uuid.uuid4().hex,
                expires_at=seen + timedelta(days=30),
                last_seen_at=seen,
                revoked_at=seen + timedelta(hours=1),
            )
        )
        await session.flush()

        body = await view(assistant_api)
        link = next(each for each in body["links"] if each["role"] == "leader")
        assert link["issued_at"] is not None
        # Погашенная сессия не стирает последний вход.
        assert link["last_login_at"] is not None
        assert abs(datetime.fromisoformat(link["last_login_at"]) - seen) < timedelta(seconds=1)


class TestShape:
    async def test_one_shape_for_both(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        leader = await view(leader_api)
        assistant = await view(assistant_api)
        assert (
            set(leader)
            == set(assistant)
            == {
                "as_of",
                "round",
                "thresholds",
                "dictionaries",
                "templates",
                "people",
                "links",
                "is_demo",
            }
        )
        week = assistant["round"]
        assert date.fromisoformat(week["week_from"]).weekday() == 0
        assert (
            date.fromisoformat(week["week_to"]) - date.fromisoformat(week["week_from"])
        ).days == 6

    async def test_nothing_without_a_link(self, api: AsyncClient) -> None:
        assert (await api.get(MANAGEMENT)).status_code == 401
