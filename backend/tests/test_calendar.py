"""API раздела «Календарь» — обещания экрана, утверждённого заказчиком 28.09.2026.

1. **Даты всех источников блока 1** в запрошенных днях: сроки проектов, вехи, задачи,
   решения руководителя, годовые циклы; сделанное — зачёркнутым, отменённого нет.
2. **Одни числа с Пультом** (инвариант 2): ступень даты — строка той же лестницы; срок
   проекта в день его вехи — одна строка со старшей ступенью (V15).
3. **«Где неделя перегружена?»** — горячие дни окна, порог и окно из справочника; ответ не
   зависит от месяца, который смотрят; прошедшие дни не горячие.
4. **«Срок прошёл»** — всё незакрытое раньше сегодняшнего, без дат циклов (V16).
5. **Годовые циклы:** даты до записи, запись, список с ближайшей датой, отмена по версии;
   смотрят оба, вносит помощник.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import local_date, now_utc
from app.domain.cycles import CycleRule, horizon, next_date, occurrences
from app.domain.decisions import DecisionKind, DecisionState
from app.domain.dictionaries import ProjectStatus, SettingKey, TaskStatus
from app.repos.models import AuditLog, LeaderDecision, LeaderQuestion, Setting, YearlyCycle
from tests.factories import make_milestone, make_person, make_project, make_task

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")
CALENDAR = "/api/v1/calendar"
CYCLES = "/api/v1/cycles"


def today() -> date:
    return local_date(now_utc(), TASHKENT)


def on(days: int) -> date:
    return today() + timedelta(days=days)


def at(day: date, hour: int = 18, minute: int = 0) -> datetime:
    """Момент по Ташкенту — срок задачи хранится в UTC (инвариант 8)."""
    return datetime.combine(day, time(hour, minute), TASHKENT).astimezone(UTC)


def window(since: date, until: date) -> str:
    return f"{CALENDAR}?from={since.isoformat()}&to={until.isoformat()}"


def by_id(items: list[dict[str, Any]], entity: object) -> dict[str, Any]:
    found = [item for item in items if item["id"] == str(entity)]
    assert found, f"даты {entity} нет в ответе"
    return found[0]


def ids(items: list[dict[str, Any]]) -> set[str]:
    return {item["id"] for item in items}


def hot_dates(days: list[dict[str, Any]]) -> list[str]:
    return [day["date"] for day in days]


async def set_threshold(session: AsyncSession, key: SettingKey, value: int) -> None:
    await session.execute(update(Setting).where(Setting.key == key.value).values(value=value))
    await session.flush()


class TestContents:
    async def test_every_source_on_its_day(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        person = await make_person(session, "Рахимов Ш.")
        project = await make_project(
            session, due_on=on(10), responsible=person, title="Цикл мониторинга: паводки"
        )
        mark = await make_milestone(
            session, project=project, due_on=on(12), title="Получение космических снимков"
        )
        task = await make_task(
            session, due_at=at(on(12)), project=project, assignee=person, title="Сводка"
        )
        decision = LeaderDecision(
            target_type="task",
            target_id=task.id,
            kind=DecisionKind.HURRY.value,
            text="Поторопить: сводка",
            assignee_person_id=person.id,
            due_on=on(12),
            state=DecisionState.OPEN.value,
        )
        session.add(decision)
        await session.flush()

        body = (await leader_api.get(window(on(0), on(20)))).json()
        assert body["range"] == {"from": on(0).isoformat(), "to": on(20).isoformat()}
        items = body["items"]
        end = by_id(items, project.id)
        assert (end["kind"], end["date"], end["owner"]) == ("project", on(10).isoformat(), None)
        assert end["target"] == {"kind": "project", "id": str(project.id)}
        assert end["responsible"]["name"] == "Рахимов Ш."

        milestone = by_id(items, mark.id)
        assert milestone["kind"] == "milestone"
        # Веха открывает карточку своего проекта; ответственный — ответственный проекта.
        assert milestone["target"] == {"kind": "project", "id": str(project.id)}
        assert milestone["owner"] == {"id": str(project.id), "title": "Цикл мониторинга: паводки"}
        assert milestone["responsible"]["name"] == "Рахимов Ш."

        work = by_id(items, task.id)
        assert (work["kind"], work["date"]) == ("task", on(12).isoformat())
        assert work["target"] == {"kind": "task", "id": str(task.id)}

        hurry = by_id(items, decision.id)
        assert (hurry["kind"], hurry["decision_kind"]) == ("decision", "hurry")
        assert hurry["title"] == "Поторопить: сводка"
        # Чьё решение — проект того, по чему оно принято; касание открывает ту задачу.
        assert hurry["owner"]["id"] == str(project.id)
        assert hurry["target"] == {"kind": "task", "id": str(task.id)}
        assert all(item["cycle"] is None and not item["ends_project"] for item in items)

    async def test_decision_opens_what_it_is_about(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(90), title="Геопортал агентства")
        mark = await make_milestone(session, project=project, due_on=on(40))
        about_project = LeaderDecision(
            target_type="project",
            target_id=project.id,
            kind=DecisionKind.ESCALATE.value,
            due_on=on(-2),
            state=DecisionState.OPEN.value,
        )
        about_mark = LeaderDecision(
            target_type="milestone",
            target_id=mark.id,
            kind=DecisionKind.HURRY.value,
            text="Поторопить: приёмка",
            due_on=on(4),
            state=DecisionState.OPEN.value,
        )
        session.add_all([about_project, about_mark])
        await session.flush()

        body = (await leader_api.get(window(on(-5), on(10)))).json()
        pult = (await leader_api.get("/api/v1/pult")).json()
        on_pult = {row["entity_id"]: (row["step"], row["deviation"]) for row in pult["rows"]}
        for decision in (about_project, about_mark):
            row = by_id(body["items"], decision.id)
            # Веха своей карточки не имеет — решение по ней открывает её проект.
            assert row["target"] == {"kind": "project", "id": str(project.id)}
            assert row["owner"]["id"] == str(project.id)
            assert on_pult[row["id"]] == (row["step"], row["deviation"])
        # Решение без текста называется видом решения — на экране, из ключа перевода.
        assert by_id(body["items"], about_project.id)["title"] is None
        assert by_id(body["items"], about_project.id)["decision_kind"] == "escalate"

    async def test_task_falls_on_its_tashkent_day(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        late = await make_task(session, due_at=at(on(5), 23, 30))
        early = await make_task(session, due_at=at(on(6), 0, 30))

        items = (await leader_api.get(window(on(5), on(6)))).json()["items"]
        # 00:30 по Ташкенту — ещё 19:30 предыдущего дня по UTC, но день — шестой.
        assert by_id(items, late.id)["date"] == on(5).isoformat()
        assert by_id(items, early.id)["date"] == on(6).isoformat()

    async def test_cancelled_is_hidden_done_is_crossed(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        cancelled = await make_project(session, due_on=on(8), status=ProjectStatus.CANCELLED)
        hidden_mark = await make_milestone(session, project=cancelled, due_on=on(8))
        dropped = await make_task(session, due_at=at(on(8)))
        dropped.status = TaskStatus.CANCELLED.value
        done_task = await make_task(session, due_at=at(on(8)))
        done_task.status = TaskStatus.DONE.value
        finished = await make_project(session, due_on=on(40), status=ProjectStatus.DONE)
        closed_mark = await make_milestone(session, project=finished, due_on=on(8))
        await session.flush()

        items = (await leader_api.get(window(on(0), on(20)))).json()["items"]
        found = ids(items)
        assert str(cancelled.id) not in found and str(hidden_mark.id) not in found
        assert str(dropped.id) not in found
        done = by_id(items, done_task.id)
        assert done["is_done"] is True and done["step"] is None
        # Веха завершённого проекта — уже не работа, как и в лестнице Пульта.
        assert by_id(items, closed_mark.id)["is_done"] is True

    async def test_only_requested_days(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        inside = await make_task(session, due_at=at(on(3)))
        outside = await make_task(session, due_at=at(on(9)))
        items = (await leader_api.get(window(on(0), on(5)))).json()["items"]
        assert str(inside.id) in ids(items) and str(outside.id) not in ids(items)
        assert [item["date"] for item in items] == sorted(item["date"] for item in items)

    async def test_window_is_checked(self, leader_api: AsyncClient) -> None:
        assert (await leader_api.get(window(on(5), on(0)))).status_code == 422
        assert (await leader_api.get(window(on(0), on(450)))).status_code == 422
        assert (await leader_api.get(window(on(0), on(449)))).status_code == 200
        assert (await leader_api.get(CALENDAR)).status_code == 422

    async def test_needs_personal_link(self, api: AsyncClient) -> None:
        assert (await api.get(window(on(0), on(5)))).status_code == 401
        assert (await api.get(CYCLES)).status_code == 401


class TestSameNumbers:
    async def test_steps_are_the_pult_steps(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(90))
        overdue = await make_milestone(session, project=project, due_on=on(-3))
        asked = await make_milestone(session, project=project, due_on=on(20))
        session.add(
            LeaderQuestion(target_type="milestone", target_id=asked.id, text="Утвердить смету?")
        )
        burning = await make_task(session, due_at=at(on(2)), project=project)
        await session.flush()

        body = (await leader_api.get(window(on(-10), on(30)))).json()
        pult = (await leader_api.get("/api/v1/pult")).json()
        on_pult = {row["entity_id"]: (row["step"], row["deviation"]) for row in pult["rows"]}
        for item in body["items"]:
            if item["kind"] == "cycle":
                continue
            if item["step"] is None:
                assert item["id"] not in on_pult
            else:
                assert on_pult[item["id"]] == (item["step"], item["deviation"])
        assert by_id(body["items"], overdue.id)["step"] == "overdue"
        assert by_id(body["items"], asked.id)["step"] == "awaiting_decision"
        assert by_id(body["items"], burning.id)["step"] == "burning"

    async def test_project_end_is_the_row_of_its_milestone(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(15))
        final = await make_milestone(session, project=project, due_on=on(15), title="Итоги")
        session.add(LeaderQuestion(target_type="project", target_id=project.id, text="Продлевать?"))
        await session.flush()

        items = (await leader_api.get(window(on(0), on(20)))).json()["items"]
        assert str(project.id) not in ids(items)
        row = by_id(items, final.id)
        assert row["ends_project"] is True
        # Ступень — старшая из двух: вопрос по проекту не пропадает оттого, что строка — веха.
        assert row["step"] == "awaiting_decision"


class TestHotDays:
    async def test_threshold_and_more_open_dates(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        for _ in range(3):
            await make_task(session, due_at=at(on(10)))
        for _ in range(2):
            await make_task(session, due_at=at(on(11)))
        done = await make_task(session, due_at=at(on(11)))
        done.status = TaskStatus.DONE.value
        await session.flush()

        body = (await leader_api.get(window(on(0), on(20)))).json()
        assert body["hot_threshold"] == 3 and body["hot_window_days"] == 28
        hot = {day["date"]: day for day in body["hot_ahead"]}
        assert hot[on(10).isoformat()]["count"] >= 3
        assert hot[on(10).isoformat()]["kinds"]["task"] >= 3
        assert on(10).isoformat() in hot_dates(body["hot_days"])

        # Проверка на своих числах: дни с другими датами базы не мешают.
        own = [item for item in body["items"] if item["date"] == on(11).isoformat()]
        open_on_11 = [item for item in own if not item["is_done"]]
        assert (on(11).isoformat() in hot) == (len(open_on_11) >= 3)

    async def test_answer_does_not_depend_on_the_month(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        for _ in range(3):
            await make_task(session, due_at=at(on(10)))
        near = (await leader_api.get(window(on(0), on(20)))).json()
        far = (await leader_api.get(window(on(200), on(230)))).json()
        assert far["hot_ahead"] == near["hot_ahead"]
        assert on(10).isoformat() in hot_dates(far["hot_ahead"])
        assert on(10).isoformat() not in hot_dates(far["hot_days"])

    async def test_threshold_and_window_come_from_settings(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        for _ in range(2):
            await make_task(session, due_at=at(on(10)))
        await set_threshold(session, SettingKey.HOT_DAY_THRESHOLD, 2)
        body = (await leader_api.get(window(on(0), on(20)))).json()
        assert body["hot_threshold"] == 2
        assert on(10).isoformat() in hot_dates(body["hot_ahead"])

        await set_threshold(session, SettingKey.HOT_WINDOW_DAYS, 7)
        body = (await leader_api.get(window(on(0), on(20)))).json()
        assert body["hot_window_days"] == 7
        assert all(day["date"] <= on(6).isoformat() for day in body["hot_ahead"])
        # Сетка своих дней считается по-прежнему: окно — только у ответа карточки.
        assert on(10).isoformat() in hot_dates(body["hot_days"])

    async def test_past_days_are_not_hot(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        late = [await make_task(session, due_at=at(on(-2))) for _ in range(3)]
        body = (await leader_api.get(window(on(-5), on(5)))).json()
        assert on(-2).isoformat() not in hot_dates(body["hot_days"])
        assert {str(task.id) for task in late} <= ids(body["overdue"])

    async def test_project_end_with_its_milestone_counts_once(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        await set_threshold(session, SettingKey.HOT_DAY_THRESHOLD, 3)
        day = on(400)
        project = await make_project(session, due_on=day)
        await make_milestone(session, project=project, due_on=day)
        await make_task(session, due_at=at(day))
        body = (await leader_api.get(window(on(380), on(420)))).json()
        on_day = [item for item in body["items"] if item["date"] == day.isoformat()]
        assert len(on_day) == 2
        assert day.isoformat() not in hot_dates(body["hot_days"])


class TestOverdue:
    async def test_project_end_with_its_milestone_is_one_row_there_too(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=on(-4))
        final = await make_milestone(session, project=project, due_on=on(-4))
        body = (await leader_api.get(window(on(30), on(60)))).json()
        assert str(project.id) not in ids(body["overdue"])
        assert by_id(body["overdue"], final.id)["ends_project"] is True

    async def test_every_open_past_date_whatever_the_month(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        old = await make_task(session, due_at=at(on(-40)))
        done = await make_task(session, due_at=at(on(-2)))
        done.status = TaskStatus.DONE.value
        project = await make_project(session, due_on=on(60))
        late_mark = await make_milestone(session, project=project, due_on=on(-5))
        session.add(
            YearlyCycle(
                title="Сведения в Кабмин",
                rule=CycleRule.QUARTERLY.value,
                month=1,
                day=5,
                every_years=1,
                anchor_year=today().year,
                is_active=True,
            )
        )
        await session.flush()

        body = (await leader_api.get(window(on(30), on(60)))).json()
        overdue = body["overdue"]
        assert {str(old.id), str(late_mark.id)} <= ids(overdue)
        assert str(done.id) not in ids(overdue)
        assert all(item["kind"] != "cycle" for item in overdue)
        assert all(item["date"] < today().isoformat() and not item["is_done"] for item in overdue)


class TestCycles:
    async def test_create_list_open_and_cancel(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        response = await assistant_api.post(
            CYCLES,
            json={
                "title": "Сведения в Кабмин по программе мониторинга",
                "rule": "quarterly",
                "month": 1,
                "day": 5,
                "every_years": 1,
                "anchor_year": today().year,
                "project_id": None,
                "responsible_id": None,
            },
        )
        assert response.status_code == 201, response.text
        created = response.json()
        expected = occurrences(
            rule=CycleRule.QUARTERLY,
            month=1,
            day=5,
            every_years=1,
            anchor_year=today().year,
            since=today(),
        )
        assert created["dates"] == [day.isoformat() for day in expected]
        assert created["next_date"] == expected[0].isoformat()

        listed = (await assistant_api.get(CYCLES)).json()
        assert created["id"] in {cycle["id"] for cycle in listed}
        assert [cycle["next_date"] for cycle in listed] == sorted(
            cycle["next_date"] for cycle in listed
        )

        body = (await assistant_api.get(window(expected[0], expected[0]))).json()
        dates = [item for item in body["items"] if item["kind"] == "cycle"]
        assert dates and dates[0]["id"] == f"{created['id']}:{expected[0].isoformat()}"
        assert dates[0]["step"] is None
        assert dates[0]["target"] == {"kind": "cycle", "id": created["id"]}
        assert dates[0]["cycle"]["rule"] == "quarterly"

        cancel = await assistant_api.post(
            f"{CYCLES}/{created['id']}/cancel", json={"version": created["version"]}
        )
        assert cancel.status_code == 204
        assert (await assistant_api.get(f"{CYCLES}/{created['id']}")).status_code == 404
        assert created["id"] not in {
            cycle["id"] for cycle in (await assistant_api.get(CYCLES)).json()
        }
        body = (await assistant_api.get(window(expected[0], expected[0]))).json()
        assert all(item["target"]["id"] != created["id"] for item in body["items"])

    async def test_cancel_by_stale_version_is_refused(self, assistant_api: AsyncClient) -> None:
        created = (
            await assistant_api.post(
                CYCLES,
                json={
                    "title": "Годовой отчёт",
                    "rule": "annual",
                    "month": 1,
                    "day": 20,
                    "every_years": 1,
                    "anchor_year": today().year,
                },
            )
        ).json()
        stale = await assistant_api.post(
            f"{CYCLES}/{created['id']}/cancel", json={"version": created["version"] + 1}
        )
        assert stale.status_code == 409
        assert (await assistant_api.get(f"{CYCLES}/{created['id']}")).status_code == 200

    async def test_cycle_without_dates_this_year_is_listed_with_next_date(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        anchor = today().year + 2
        session.add(
            YearlyCycle(
                title="Переаттестация операторов",
                rule=CycleRule.EVERY_N_YEARS.value,
                month=1,
                day=20,
                every_years=2,
                anchor_year=anchor,
                is_active=True,
            )
        )
        await session.flush()
        listed = (await leader_api.get(CYCLES)).json()
        found = next(cycle for cycle in listed if cycle["title"] == "Переаттестация операторов")
        assert found["next_date"] == date(anchor, 1, 20).isoformat()
        detail = (await leader_api.get(f"{CYCLES}/{found['id']}")).json()
        assert detail["dates"] == []

    async def test_cycle_dates_stop_at_the_horizon(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        edge = horizon(today())
        session.add(
            YearlyCycle(
                title="Сведения в Кабмин",
                rule=CycleRule.QUARTERLY.value,
                month=1,
                day=5,
                every_years=1,
                anchor_year=today().year,
                is_active=True,
            )
        )
        await session.flush()
        # Сто дней по обе стороны горизонта — в них не меньше одной квартальной даты с
        # каждой стороны.
        body = (
            await leader_api.get(window(edge - timedelta(days=100), edge + timedelta(days=100)))
        ).json()
        assert body["horizon_to"] == edge.isoformat()
        cycles = [item["date"] for item in body["items"] if item["kind"] == "cycle"]
        assert cycles and all(day <= edge.isoformat() for day in cycles)

    async def test_past_date_of_a_cycle_is_shown_without_step(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        session.add(
            YearlyCycle(
                title="Сводка о снимках",
                rule=CycleRule.QUARTERLY.value,
                month=1,
                day=5,
                every_years=1,
                anchor_year=today().year,
                is_active=True,
            )
        )
        await session.flush()
        body = (await leader_api.get(window(on(-100), on(-1)))).json()
        past = [item for item in body["items"] if item["kind"] == "cycle"]
        assert past and all(item["step"] is None and not item["is_done"] for item in past)

    async def test_preview_writes_nothing_and_both_can_ask(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        before = await session.scalar(select(func.count()).select_from(YearlyCycle))
        rule = {
            "rule": "every_n_years",
            "month": 1,
            "day": 20,
            "every_years": 3,
            "anchor_year": today().year,
        }
        body = (await leader_api.post(f"{CYCLES}/preview", json=rule)).json()
        expected = next_date(
            rule=CycleRule.EVERY_N_YEARS,
            month=1,
            day=20,
            every_years=3,
            anchor_year=today().year,
            since=today(),
        )
        assert body["next_date"] == (expected.isoformat() if expected else None)
        never = (
            await leader_api.post(
                f"{CYCLES}/preview", json={**rule, "rule": "annual", "month": 2, "day": 30}
            )
        ).json()
        assert never == {"dates": [], "next_date": None}
        assert await session.scalar(select(func.count()).select_from(YearlyCycle)) == before

    async def test_create_refuses_what_never_happens(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        base: dict[str, Any] = {
            "title": "Цикл",
            "rule": "annual",
            "month": 1,
            "day": 20,
            "every_years": 1,
            "anchor_year": today().year,
        }
        cases: list[dict[str, Any]] = [
            {"month": 2, "day": 30},
            {"rule": "every_n_years", "every_years": 1},
            {"rule": "every_n_years", "every_years": 3, "anchor_year": today().year + 11},
            {"title": "   "},
            {"month": 13},
        ]
        for case in cases:
            response = await assistant_api.post(CYCLES, json={**base, **case})
            assert response.status_code == 422, (case, response.text)

        done = await make_project(session, due_on=on(30), status=ProjectStatus.DONE)
        response = await assistant_api.post(CYCLES, json={**base, "project_id": str(done.id)})
        assert response.status_code == 422
        missing = "00000000-0000-0000-0000-000000000001"
        assert (
            await assistant_api.post(CYCLES, json={**base, "project_id": missing})
        ).status_code == 404
        assert (
            await assistant_api.post(CYCLES, json={**base, "responsible_id": missing})
        ).status_code == 404

    async def test_leader_looks_but_does_not_write(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        cycle = YearlyCycle(
            title="Годовой отчёт",
            rule=CycleRule.ANNUAL.value,
            month=1,
            day=20,
            every_years=1,
            anchor_year=today().year,
            is_active=True,
        )
        session.add(cycle)
        await session.flush()
        assert (await leader_api.get(f"{CYCLES}/{cycle.id}")).status_code == 200
        response = await leader_api.post(
            CYCLES,
            json={
                "title": "Цикл",
                "rule": "annual",
                "month": 1,
                "day": 20,
                "every_years": 1,
                "anchor_year": today().year,
            },
        )
        assert response.status_code == 403
        cancel = await leader_api.post(f"{CYCLES}/{cycle.id}/cancel", json={"version": 1})
        assert cancel.status_code == 403

    async def test_every_change_is_in_the_journal(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        async def journal() -> int:
            count = await session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.entity_type == YearlyCycle.__tablename__)
            )
            return count or 0

        before = await journal()
        created = (
            await assistant_api.post(
                CYCLES,
                json={
                    "title": "Годовой отчёт",
                    "rule": "annual",
                    "month": 1,
                    "day": 20,
                    "every_years": 1,
                    "anchor_year": today().year,
                },
            )
        ).json()
        assert await journal() == before + 1
        await assistant_api.post(
            f"{CYCLES}/{created['id']}/cancel", json={"version": created["version"]}
        )
        assert await journal() == before + 2
