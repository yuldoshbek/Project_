"""API раздела «Программы» — обещания экрана, утверждённого заказчиком 27.09.2026.

1. **Одни числа с Пультом и «Проектами»** (инвариант 2): ступени программ, подпроектов и
   вех — строки той же лестницы; готовность и отставание программы — те же, что в её
   карточке в «Проектах», вместе с подпроектами (V13).
2. **Горизонт лет, отсчёт до даты, исходные сроки** (критерий ТЗ 11).
3. **«Что должно случиться до конца года?»** — непройденные вехи программ и подпроектов
   до 31 декабря, по сроку.
4. **«Успеваем ли к дате программы?»** — по темпу за 90 дней; меньше 10 закрытых задач —
   «мало данных» (ТЗ 4; V13).
5. Раздел только читает; смотрят оба.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import local_date, now_utc
from app.domain.dictionaries import ProjectStatus, TaskStatus
from app.repos.models import AuditLog, LeaderQuestion, Milestone, Project
from app.services import metrics
from tests.factories import make_milestone, make_person, make_project, make_task

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")
PROGRAMS = "/api/v1/programs"


def today() -> date:
    return local_date(now_utc(), TASHKENT)


def on(days: int) -> date:
    return today() + timedelta(days=days)


def ago(days: int) -> datetime:
    """Момент дня `days` дней назад по Ташкенту — середина дня, чтобы не спорить с полуночью."""
    return datetime.combine(on(-days), time(12), TASHKENT).astimezone(UTC)


async def make_program(
    session: AsyncSession, *, due_on: date, status: ProjectStatus = ProjectStatus.IN_PROGRESS
) -> Project:
    program = await make_project(session, due_on=due_on, status=status)
    program.is_multiyear = True
    await session.flush()
    return program


async def make_subproject(
    session: AsyncSession,
    program: Project,
    *,
    due_on: date,
    status: ProjectStatus = ProjectStatus.IN_PROGRESS,
) -> Project:
    sub = await make_project(session, due_on=due_on, status=status)
    sub.parent_project_id = program.id
    await session.flush()
    return sub


async def close_tasks(
    session: AsyncSession,
    project: Project,
    count: int,
    *,
    days_ago: int = 5,
    status: TaskStatus = TaskStatus.DONE,
) -> None:
    for _ in range(count):
        task = await make_task(session, due_at=None, project=project)
        task.status = status.value
        task.completed_at = ago(days_ago)
    await session.flush()


async def pass_milestone(milestone: Milestone, *, passed_on: date, session: AsyncSession) -> None:
    milestone.is_passed = True
    milestone.passed_on = passed_on
    await session.flush()


def item_of(body: dict[str, Any], project: Project) -> dict[str, Any]:
    found: list[dict[str, Any]] = [item for item in body["items"] if item["id"] == str(project.id)]
    assert found, f"программы {project.title} нет в ответе"
    return found[0]


class TestContents:
    async def test_only_programmes_with_subprojects_inside(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(700))
        sub = await make_subproject(session, program, due_on=on(300))
        plain = await make_project(session, due_on=on(60))

        body = (await leader_api.get(PROGRAMS)).json()
        ids = [item["id"] for item in body["items"]]
        assert ids == [str(program.id)]
        assert str(plain.id) not in ids and str(sub.id) not in ids
        assert [each["id"] for each in item_of(body, program)["subprojects"]] == [str(sub.id)]

    async def test_horizon_is_five_years_from_the_current(self, assistant_api: AsyncClient) -> None:
        body = (await assistant_api.get(PROGRAMS)).json()
        year = today().year
        assert body["horizon"] == {"from": year, "to": year + 4}
        assert body["items"] == [] and body["year_end"] == []
        assert "as_of" in body and "is_demo" in body

    async def test_countdown_and_original_dates(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(591))
        program.original_due_on = on(500)
        late = await make_milestone(session, project=program, due_on=on(120), title="Договор")
        late.original_due_on = on(80)
        early = await make_milestone(session, project=program, due_on=on(3), title="Согласование")
        await session.flush()

        item = item_of((await leader_api.get(PROGRAMS)).json(), program)
        assert item["days_left"] == 591
        assert item["original_due_on"] == on(500).isoformat()
        # По сроку, а не по порядку вех проекта: «далее» — ближайшая непройденная.
        assert [mark["id"] for mark in item["milestones"]] == [str(early.id), str(late.id)]
        assert item["milestones"][1]["original_due_on"] == on(80).isoformat()
        assert [mark["days_left"] for mark in item["milestones"]] == [3, 120]


class TestSameNumbers:
    async def test_steps_are_the_pult_steps(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(400))
        overdue = await make_milestone(session, project=program, due_on=on(-4))
        asked = await make_milestone(session, project=program, due_on=on(60))
        session.add(
            LeaderQuestion(target_type="milestone", target_id=asked.id, text="Утвердить смету?")
        )
        sub = await make_subproject(session, program, due_on=on(5))
        await session.flush()

        body = (await leader_api.get(PROGRAMS)).json()
        pult = (await leader_api.get("/api/v1/pult")).json()
        on_pult = {
            row["entity_id"]: (row["step"], row["deviation"])
            for row in pult["rows"]
            if row["section"] in ("projects", "milestones")
        }
        item = item_of(body, program)
        rows = [item, *item["subprojects"], *item["milestones"]]
        rows += [mark for each in item["subprojects"] for mark in each["milestones"]]
        for row in rows:
            if row["step"] is None:
                assert row["id"] not in on_pult
            else:
                assert on_pult[row["id"]] == (row["step"], row["deviation"])
        steps = {mark["id"]: mark["step"] for mark in item["milestones"]}
        assert steps[str(overdue.id)] == "overdue"
        assert steps[str(asked.id)] == "awaiting_decision"
        assert item["subprojects"][0]["id"] == str(sub.id)
        assert item["subprojects"][0]["step"] == "burning"

    async def test_readiness_with_subprojects_matches_the_project_card(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(300))
        passed = await make_milestone(session, project=program, due_on=on(-30))
        await pass_milestone(passed, passed_on=on(-30), session=session)
        await make_milestone(session, project=program, due_on=on(100))
        sub = await make_subproject(session, program, due_on=on(200))
        await make_milestone(session, project=sub, due_on=on(150))
        await close_tasks(session, sub, 3)
        await make_task(session, due_at=None, project=sub)
        # Отменённая в счёт не входит — ни в готовность, ни в остаток.
        await close_tasks(session, sub, 1, status=TaskStatus.CANCELLED)

        expected = metrics.progress(
            status=ProjectStatus.IN_PROGRESS,
            started_on=program.started_on,
            due_on=program.due_on,
            today=today(),
            work=metrics.Work(passed_milestones=1, total_milestones=3, done_tasks=3, total_tasks=4),
        )
        item = item_of((await leader_api.get(PROGRAMS)).json(), program)
        assert (item["readiness"], item["lag_days"]) == (expected.readiness, expected.lag_days)
        assert item["readiness"] == 57

        projects = (await leader_api.get("/api/v1/projects")).json()
        card = next(each for each in projects["items"] if each["id"] == str(program.id))
        assert (card["readiness"], card["lag_days"]) == (item["readiness"], item["lag_days"])
        detail = (await leader_api.get(f"/api/v1/projects/{program.id}")).json()
        assert detail["readiness"] == item["readiness"]
        # Подпроект считается сам по себе: веха и четыре задачи, три закрыты.
        assert item["subprojects"][0]["readiness"] == 60

    async def test_what_if_lag_of_a_programme_counts_subprojects(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(300))
        sub = await make_subproject(session, program, due_on=on(200))
        await close_tasks(session, sub, 2)
        await make_task(session, due_at=None, project=sub)

        item = item_of((await leader_api.get(PROGRAMS)).json(), program)
        body = (
            await leader_api.post(
                f"/api/v1/projects/{program.id}/what-if",
                json={
                    "changes": [
                        {"kind": "project", "id": str(program.id), "due_on": on(300).isoformat()}
                    ]
                },
            )
        ).json()
        assert body["project"]["before"]["lag_days"] == item["lag_days"]


class TestClosedSubprojects:
    """Закрытый подпроект своё не держит (V13): завершённый — сделан, у отменённого —
    только сделанное. Одинаково в «Программах» и в карточке проекта."""

    async def test_cancelled_keeps_only_what_was_done(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(300))
        own = await make_milestone(session, project=program, due_on=on(-20))
        await pass_milestone(own, passed_on=on(-20), session=session)
        await make_milestone(session, project=program, due_on=on(100))
        cut = await make_subproject(session, program, due_on=on(200))
        done_mark = await make_milestone(session, project=cut, due_on=on(-10))
        await pass_milestone(done_mark, passed_on=on(-10), session=session)
        for days in (50, 80, 120):
            await make_milestone(session, project=cut, due_on=on(days))
        await close_tasks(session, cut, 2)
        for _ in range(5):
            await make_task(session, due_at=None, project=cut)
        cut.status_code = ProjectStatus.CANCELLED.value
        cut.status_reason = "урезали объём"
        await session.flush()

        # Своё: веха из двух пройдена. Отменённый: пройденная веха и две задачи — сделаны,
        # три вехи и пять задач не сделают. Итого закрыто 4 из 5.
        item = item_of((await leader_api.get(PROGRAMS)).json(), program)
        assert item["readiness"] == 80
        assert item["pace"]["remaining"] == 1
        detail = (await leader_api.get(f"/api/v1/projects/{program.id}")).json()
        assert detail["readiness"] == item["readiness"]

    async def test_done_counts_as_done(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(300))
        await make_milestone(session, project=program, due_on=on(100))
        finished = await make_subproject(session, program, due_on=on(-5), status=ProjectStatus.DONE)
        # Забытая непройденная веха завершённого подпроекта: «завершён» — последнее слово.
        await make_milestone(session, project=finished, due_on=on(-7))
        await make_task(session, due_at=None, project=finished)

        item = item_of((await leader_api.get(PROGRAMS)).json(), program)
        assert item["readiness"] == 67
        assert item["pace"]["remaining"] == 1
        assert item["subprojects"][0]["readiness"] == 100
        projects = (await leader_api.get("/api/v1/projects")).json()
        card = next(each for each in projects["items"] if each["id"] == str(program.id))
        assert card["readiness"] == item["readiness"]


class TestYearEnd:
    async def test_open_milestones_until_december_by_date(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(900))
        late = await make_milestone(session, project=program, due_on=on(-10), title="Площадка")
        due_today = await make_milestone(session, project=program, due_on=on(0), title="Сегодня")
        done = await make_milestone(session, project=program, due_on=on(0), title="Пройдена")
        await pass_milestone(done, passed_on=on(0), session=session)
        await make_milestone(
            session, project=program, due_on=date(today().year + 1, 1, 15), title="Следующий год"
        )
        sub = await make_subproject(session, program, due_on=on(400))
        sub_mark = await make_milestone(session, project=sub, due_on=on(-2), title="Подпроект")
        closed_sub = await make_subproject(
            session, program, due_on=on(400), status=ProjectStatus.CANCELLED
        )
        await make_milestone(session, project=closed_sub, due_on=on(-1), title="Отменённый")
        finished = await make_program(session, due_on=on(-5), status=ProjectStatus.DONE)
        await make_milestone(session, project=finished, due_on=on(-5), title="Закрытая программа")

        rows = (await leader_api.get(PROGRAMS)).json()["year_end"]
        assert [row["milestone"]["id"] for row in rows] == [
            str(late.id),
            str(sub_mark.id),
            str(due_today.id),
        ]
        assert rows[0]["program"] == {
            "id": str(program.id),
            "code": program.code,
            "title": program.title,
        }
        assert rows[0]["subproject"] is None
        assert rows[1]["subproject"] == {"id": str(sub.id), "title": sub.title}
        assert rows[0]["milestone"]["step"] == "overdue"

    async def test_responsible_of_the_owner(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(900))
        person = await make_person(session, "Каримов А.")
        sub = await make_subproject(session, program, due_on=on(400))
        sub.responsible_person_id = person.id
        await make_milestone(session, project=sub, due_on=on(1))
        await session.flush()

        row = (await leader_api.get(PROGRAMS)).json()["year_end"][0]
        assert row["responsible"] == {"id": str(person.id), "name": "Каримов А."}

    async def test_closed_programme_keeps_its_open_subprojects(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(-5), status=ProjectStatus.DONE)
        await make_milestone(session, project=program, due_on=on(-6), title="Своя")
        sub = await make_subproject(session, program, due_on=on(100))
        late = await make_milestone(session, project=sub, due_on=on(-4), title="Подпроекта")

        body = (await leader_api.get(PROGRAMS)).json()
        rows = body["year_end"]
        # Своя веха закрытой программы не должна случиться; веха идущего подпроекта — должна
        # и стоит на Пульте просроченной.
        assert [row["milestone"]["id"] for row in rows] == [str(late.id)]
        assert rows[0]["milestone"]["step"] == "overdue"
        pult = (await leader_api.get("/api/v1/pult")).json()
        assert any(row["entity_id"] == str(late.id) for row in pult["rows"])


class TestPace:
    async def test_behind_by_the_pace_of_ninety_days(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(45))
        sub = await make_subproject(session, program, due_on=on(40))
        await close_tasks(session, program, 6, days_ago=10)
        await close_tasks(session, sub, 4, days_ago=80)
        # Закрытое раньше окна — не темп: 91 день назад.
        await close_tasks(session, program, 5, days_ago=91)
        recent = await make_milestone(session, project=program, due_on=on(-3))
        await pass_milestone(recent, passed_on=on(-3), session=session)
        for _ in range(7):
            await make_task(session, due_at=None, project=program)
        await make_milestone(session, project=sub, due_on=on(30))

        pace = item_of((await leader_api.get(PROGRAMS)).json(), program)["pace"]
        # Закрыто за окно: 10 задач и веха; осталось 7 задач и веха подпроекта.
        assert pace["closed"] == 11
        assert pace["closed_tasks"] == 10
        assert pace["remaining"] == 8
        assert pace["window_days"] == 90
        assert pace["min_closed_tasks"] == 10
        need = -(-8 * 90 // 11)
        assert pace["forecast_on"] == on(need).isoformat()
        assert pace["gap_days"] == need - 45
        assert pace["verdict"] == "behind"

    async def test_little_data_below_ten_closed_tasks(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(700))
        await close_tasks(session, program, 9)
        await close_tasks(session, program, 3, status=TaskStatus.CANCELLED)

        pace = item_of((await leader_api.get(PROGRAMS)).json(), program)["pace"]
        assert pace["verdict"] == "little_data"
        assert (pace["closed_tasks"], pace["forecast_on"], pace["gap_days"]) == (9, None, None)

    async def test_on_track_with_room(self, leader_api: AsyncClient, session: AsyncSession) -> None:
        program = await make_program(session, due_on=on(700))
        await close_tasks(session, program, 12)
        await make_task(session, due_at=None, project=program)

        pace = item_of((await leader_api.get(PROGRAMS)).json(), program)["pace"]
        assert pace["verdict"] == "on_track"
        assert pace["gap_days"] < 0

    async def test_closed_programme_is_not_asked(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        program = await make_program(session, due_on=on(-5), status=ProjectStatus.DONE)
        await close_tasks(session, program, 12)

        item = item_of((await leader_api.get(PROGRAMS)).json(), program)
        assert item["pace"] is None
        assert (item["readiness"], item["lag_days"]) == (100, 0)


class TestOrderAndAccess:
    async def test_ladder_first_then_by_date_closed_last(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        closed = await make_program(session, due_on=on(-50), status=ProjectStatus.DONE)
        later = await make_program(session, due_on=on(900))
        sooner = await make_program(session, due_on=on(500))
        burning = await make_program(session, due_on=on(3))

        ids = [item["id"] for item in (await leader_api.get(PROGRAMS)).json()["items"]]
        assert ids == [str(burning.id), str(sooner.id), str(later.id), str(closed.id)]

    async def test_equal_dates_keep_one_order(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        first = await make_program(session, due_on=on(900))
        second = await make_program(session, due_on=on(900))
        expected = sorted([first, second], key=lambda each: each.code)

        ids = [item["id"] for item in (await leader_api.get(PROGRAMS)).json()["items"]]
        assert ids == [str(each.id) for each in expected]
        # Правка записи меняет её место в таблице базы, но не в разделе.
        second.title = "Переименована"
        await session.flush()
        again = [item["id"] for item in (await leader_api.get(PROGRAMS)).json()["items"]]
        assert again == ids

    async def test_both_read_nothing_is_written(
        self,
        leader_api: AsyncClient,
        assistant_api: AsyncClient,
        session: AsyncSession,
    ) -> None:
        await make_program(session, due_on=on(400))
        before = await session.scalar(select(func.count()).select_from(AuditLog))
        assert (await leader_api.get(PROGRAMS)).status_code == 200
        assert (await assistant_api.get(PROGRAMS)).status_code == 200
        assert await session.scalar(select(func.count()).select_from(AuditLog)) == before

    async def test_without_a_link_nothing(self, api: AsyncClient) -> None:
        assert (await api.get(PROGRAMS)).status_code == 401
