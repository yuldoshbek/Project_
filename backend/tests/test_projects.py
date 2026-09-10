"""Проекты (ORB-011).

Проверяются пять обещаний карточки и одно, которое в ней не записано, но дороже всех:
светофор считается **в одном месте**. На него смотрят карточка проекта, дашборд, сводка в
Telegram и ответ SETA; две реализации одного правила разойдутся в цифрах, и доверия не
будет ни к одной.

Правило светофора проверяется таблицей на граничных датах, без базы: граница «сегодня —
последний день срока» отделяет жёлтый от красного, и ошибка в ней означает, что
руководителю показали красную зону там, где её нет, или не показали там, где есть.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import today_in
from app.domain.dictionaries import Health, Priority, ProjectStatus
from app.domain.projects import (
    Classification,
    ProjectKind,
    auto_progress,
    health,
)
from app.repos.models import AuditLog, Direction, Person, Project
from app.services import projects as service

pytestmark = pytest.mark.infra

# Тридцатидневный срок: на нём и дни, и доля пройденного времени дают целые границы.
STARTED = date(2026, 1, 1)
DUE = date(2026, 1, 31)
WARN_DAYS = 3
WARN_RATIO = 0.8


def colour(
    today: date, *, status: ProjectStatus = ProjectStatus.IN_PROGRESS, warn: int = WARN_DAYS
) -> Health:
    return health(
        status=status,
        started_on=STARTED,
        due_on=DUE,
        today=today,
        warn_days=warn,
        warn_ratio=WARN_RATIO,
    )


class TestTrafficLight:
    """[ADR-0005](../../docs/adr/ADR-0005-traffic-light.md), граничные даты."""

    @pytest.mark.parametrize(
        ("today", "expected", "why"),
        [
            (date(2026, 1, 1), Health.GREEN, "первый день: не прошло ничего"),
            (date(2026, 1, 25), Health.GREEN, "прошло ровно 80% — «более» ещё не наступило"),
            (date(2026, 1, 26), Health.YELLOW, "прошло 83%: перевалило за порог"),
            (date(2026, 1, 28), Health.YELLOW, "до срока ровно warn_days"),
            (date(2026, 1, 31), Health.YELLOW, "сегодня последний день срока — ещё не просрочка"),
            (date(2026, 2, 1), Health.RED, "срок вчера: просрочено (ADR-0004)"),
            (date(2025, 12, 25), Health.GREEN, "проект ещё не начат: доля не бывает отрицательной"),
        ],
    )
    def test_boundaries(self, today: date, expected: Health, why: str) -> None:
        assert colour(today) is expected, why

    @pytest.mark.parametrize("status", [ProjectStatus.DONE, ProjectStatus.CANCELLED])
    def test_finished_projects_leave_the_traffic_light(self, status: ProjectStatus) -> None:
        """Серый — не «нет данных», а «исключён».

        Без этого доля зелёного росла бы по мере завершения работ и перестала бы
        что-либо значить.
        """
        assert colour(date(2026, 2, 1), status=status) is Health.GREY

    def test_urgent_is_yellow_from_the_first_day_and_red_the_next(self) -> None:
        """Для «Срочно» `warn_days` равен нулю (ADR-0005)."""
        assert colour(DUE, warn=0) is Health.YELLOW
        assert colour(DUE + timedelta(days=1), warn=0) is Health.RED

    def test_a_deadline_equal_to_the_start_counts_as_fully_elapsed(self) -> None:
        """Однодневный срок исчерпан целиком: делить на ноль нечего.

        Путь через долю времени, а не через остаток дней: проект начинается и кончается
        в один день, а смотрим на него заранее.
        """
        same = date(2026, 5, 5)
        assert (
            health(
                status=ProjectStatus.IN_PROGRESS,
                started_on=same,
                due_on=same,
                today=date(2026, 5, 1),
                warn_days=0,
                warn_ratio=WARN_RATIO,
            )
            is Health.YELLOW
        )

    def test_a_single_day_deadline_does_not_divide_by_zero(self) -> None:
        same = date(2026, 5, 5)
        assert (
            health(
                status=ProjectStatus.IN_PROGRESS,
                started_on=same,
                due_on=same,
                today=same,
                warn_days=0,
                warn_ratio=WARN_RATIO,
            )
            is Health.YELLOW
        )


class TestMiniProjects:
    def test_a_mini_project_needs_no_milestones(self) -> None:
        """Требовать вехи от недельной работы — значит заставить их придумать.

        Придуманные этапы никто не закрывает, и через месяц все мини-проекты выглядят
        просроченными. Тогда светофор перестают читать, а он и есть продукт.
        """
        assert ProjectKind.MINI.requires_milestones is False
        assert ProjectKind.PROJECT.requires_milestones is True


class TestAutoProgress:
    """Расчёт доли выполненного. Привязка к смене статуса задачи — ORB-014."""

    @pytest.mark.parametrize(
        ("total", "done", "expected"),
        [(0, 0, 0), (4, 1, 25), (3, 1, 33), (3, 2, 67), (5, 5, 100)],
    )
    def test_share_of_completed_tasks(self, total: int, done: int, expected: int) -> None:
        assert auto_progress(total_tasks=total, done_tasks=done) == expected

    def test_a_project_without_tasks_is_zero_not_a_hundred(self) -> None:
        """Пустота не является завершённостью."""
        assert auto_progress(total_tasks=0, done_tasks=0) == 0


async def a_direction(session: AsyncSession) -> Direction:
    direction = await session.scalar(select(Direction).limit(1))
    assert direction is not None, "справочник направлений пуст — сиды не загрузились"
    return direction


async def payload(session: AsyncSession, **overrides: Any) -> dict[str, Any]:
    direction = await a_direction(session)
    body: dict[str, Any] = {
        "title": "Космический мониторинг сельхозугодий",
        "direction_id": str(direction.id),
        "status_code": ProjectStatus.IN_PROGRESS.value,
        "priority_code": Priority.NORMAL.value,
        "started_on": "2026-01-01",
        "due_on": "2026-12-31",
    }
    body.update(overrides)
    return body


class TestWhoMayWrite:
    async def test_assistant_creates_reads_changes_and_deletes(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        created = await assistant_api.post("/api/v1/projects", json=await payload(session))
        assert created.status_code == 201, created.text
        project_id = created.json()["id"]

        assert (await assistant_api.get(f"/api/v1/projects/{project_id}")).status_code == 200

        changed = await assistant_api.patch(
            f"/api/v1/projects/{project_id}", json={"title": "Новое название"}
        )
        assert changed.status_code == 200
        assert changed.json()["title"] == "Новое название"

        assert (await assistant_api.delete(f"/api/v1/projects/{project_id}")).status_code == 204
        assert (await assistant_api.get(f"/api/v1/projects/{project_id}")).status_code == 404

    async def test_leader_reads_but_changes_nothing(
        self, leader_api: AsyncClient, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Решение по проекту на контроле — единственное исключение, и это ORB-062."""
        created = await assistant_api.post("/api/v1/projects", json=await payload(session))
        project_id = created.json()["id"]

        assert (await leader_api.get("/api/v1/projects")).status_code == 200
        assert (await leader_api.get(f"/api/v1/projects/{project_id}")).status_code == 200

        assert (
            await leader_api.post("/api/v1/projects", json=await payload(session))
        ).status_code == 403
        assert (
            await leader_api.patch(f"/api/v1/projects/{project_id}", json={"title": "Правка"})
        ).status_code == 403
        assert (await leader_api.delete(f"/api/v1/projects/{project_id}")).status_code == 403


class TestRulesRefuseBadData:
    async def test_pausing_without_a_reason_is_refused_with_an_explanation(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Без причины через месяц никто не помнит, чего ждёт приостановленный проект."""
        response = await assistant_api.post(
            "/api/v1/projects",
            json=await payload(session, status_code=ProjectStatus.ON_HOLD.value),
        )

        assert response.status_code == 422
        body = response.json()
        assert body["type"].endswith("rule-violation")
        assert "причин" in body["detail"].lower(), "текст обязан называть, чего не хватает"

    async def test_pausing_a_running_project_without_a_reason_is_refused_too(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Проверка на изменении, а не только на создании: обойти её было бы легко."""
        created = await assistant_api.post("/api/v1/projects", json=await payload(session))
        project_id = created.json()["id"]

        response = await assistant_api.patch(
            f"/api/v1/projects/{project_id}",
            json={"status_code": ProjectStatus.ON_HOLD.value},
        )

        assert response.status_code == 422

    async def test_pausing_with_a_reason_is_allowed(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        response = await assistant_api.post(
            "/api/v1/projects",
            json=await payload(
                session,
                status_code=ProjectStatus.ON_HOLD.value,
                status_reason="Ждём подписания межведомственного соглашения",
            ),
        )

        assert response.status_code == 201

    async def test_a_deadline_before_the_start_is_refused(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        response = await assistant_api.post(
            "/api/v1/projects",
            json=await payload(session, started_on="2026-06-01", due_on="2026-05-01"),
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "раньше даты начала" in detail, "объяснение потерялось"
        assert "2026-05-01" in detail, "подробность потерялась"

    async def test_progress_beyond_a_hundred_is_refused(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        response = await assistant_api.post(
            "/api/v1/projects", json=await payload(session, progress_pct=140)
        )

        assert response.status_code == 422


class TestCode:
    async def test_numbers_run_in_sequence_within_the_year(
        self, session: AsyncSession, assistant_api: AsyncClient
    ) -> None:
        first = await assistant_api.post("/api/v1/projects", json=await payload(session))
        second = await assistant_api.post("/api/v1/projects", json=await payload(session))

        codes = [first.json()["code"], second.json()["code"]]
        year = today_in("Asia/Tashkent").year
        assert all(code.startswith(f"PRJ-{year}-") for code in codes), codes
        assert int(codes[1][-3:]) == int(codes[0][-3:]) + 1

    async def test_the_number_follows_the_tail_not_the_string(self, session: AsyncSession) -> None:
        """На тысячном проекте года строковое сравнение поставило бы 1000 раньше 999.

        Номер начал бы повторяться, а уникальность превратила бы это в отказ заводить
        новые проекты — в декабре, без объяснения.
        """
        direction = await a_direction(session)
        session.add(
            Project(
                code="PRJ-2030-999",
                title="Девятьсот девяносто девятый",
                kind=ProjectKind.PROJECT.value,
                classification=Classification.INTERNAL.value,
                direction_id=direction.id,
                status_code=ProjectStatus.IN_PROGRESS.value,
                priority_code=Priority.NORMAL.value,
                started_on=date(2030, 1, 1),
                due_on=date(2030, 12, 31),
            )
        )
        await session.flush()

        assert await service.next_code(session, today=date(2030, 6, 1)) == "PRJ-2030-1000"


class TestEveryChangeIsInTheJournal:
    async def test_creation_and_change_leave_a_trail(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        created = await assistant_api.post("/api/v1/projects", json=await payload(session))
        project_id = uuid.UUID(created.json()["id"])

        await assistant_api.patch(
            f"/api/v1/projects/{project_id}", json={"title": "Уточнённое название"}
        )

        entries = list(
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.entity_id == project_id)
                .order_by(AuditLog.occurred_at)
            )
        )
        assert [entry.action for entry in entries] == ["created", "updated"]
        assert entries[0].entity_type == "projects"
        assert list(entries[1].changes) == ["title"], "в записи оказалось лишнее поле"
        assert entries[1].changes["title"]["to"] == "Уточнённое название"

    async def test_a_classified_project_is_logged_without_its_content(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Факт изменения фиксируется, содержимое — нет (ADR-0007, ORB-009)."""
        created = await assistant_api.post(
            "/api/v1/projects",
            json=await payload(
                session,
                title="Название закрытого проекта",
                classification=Classification.RESTRICTED.value,
            ),
        )
        project_id = uuid.UUID(created.json()["id"])

        entry = await session.scalar(select(AuditLog).where(AuditLog.entity_id == project_id))
        assert entry is not None
        assert "title" in entry.changes, "факт изменения обязан остаться"
        assert entry.changes["title"]["to"] == "***"
        assert "Название закрытого проекта" not in str(entry.changes)


class TestListing:
    async def test_filters_narrow_the_portfolio(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        await assistant_api.post(
            "/api/v1/projects", json=await payload(session, title="Мониторинг посевов")
        )
        await assistant_api.post(
            "/api/v1/projects",
            json=await payload(
                session,
                title="Соглашение с ЕКА",
                priority_code=Priority.URGENT.value,
                kind=ProjectKind.MINI.value,
            ),
        )

        urgent = await assistant_api.get(
            "/api/v1/projects", params={"priority_code": Priority.URGENT.value}
        )
        assert [item["title"] for item in urgent.json()] == ["Соглашение с ЕКА"]

        found = await assistant_api.get("/api/v1/projects", params={"search": "посев"})
        assert [item["title"] for item in found.json()] == ["Мониторинг посевов"]

        mini = await assistant_api.get("/api/v1/projects", params={"kind": ProjectKind.MINI.value})
        assert [item["title"] for item in mini.json()] == ["Соглашение с ЕКА"]

    async def test_the_remaining_filters_narrow_the_portfolio_too(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Направление, статус, гриф и куратор.

        Проверяются вместе с остальными: фильтр, который никто не звал, однажды
        оказывается сломан ровно в тот день, когда он понадобился на докладе.
        """
        directions = list(await session.scalars(select(Direction).order_by(Direction.code)))
        assert len(directions) >= 2, "для проверки нужно два направления"

        curator = Person(full_name="Куратор Направления")
        session.add(curator)
        await session.flush()

        await assistant_api.post(
            "/api/v1/projects",
            json=await payload(
                session,
                title="Первое направление",
                direction_id=str(directions[0].id),
                curator_person_id=str(curator.id),
            ),
        )
        await assistant_api.post(
            "/api/v1/projects",
            json=await payload(
                session,
                title="Второе направление",
                direction_id=str(directions[1].id),
                status_code=ProjectStatus.AWAITING_DECISION.value,
                classification=Classification.RESTRICTED.value,
            ),
        )

        async def titles(**params: Any) -> list[str]:
            response = await assistant_api.get("/api/v1/projects", params=params)
            return [item["title"] for item in response.json()]

        assert await titles(direction_id=str(directions[1].id)) == ["Второе направление"]
        assert await titles(status_code=ProjectStatus.AWAITING_DECISION.value) == [
            "Второе направление"
        ]
        assert await titles(classification=Classification.RESTRICTED.value) == [
            "Второе направление"
        ]
        assert await titles(curator_person_id=str(curator.id)) == ["Первое направление"]

    async def test_sorting_is_applied_and_reversible(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        await assistant_api.post(
            "/api/v1/projects", json=await payload(session, title="Б", due_on="2026-03-01")
        )
        await assistant_api.post(
            "/api/v1/projects", json=await payload(session, title="А", due_on="2026-02-01")
        )

        ascending = await assistant_api.get("/api/v1/projects", params={"sort_by": "due_on"})
        descending = await assistant_api.get(
            "/api/v1/projects", params={"sort_by": "due_on", "descending": True}
        )

        assert [item["title"] for item in ascending.json()] == ["А", "Б"]
        assert [item["title"] for item in descending.json()] == ["Б", "А"]

    async def test_the_colour_comes_with_the_project(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Список без светофора бесполезен, а второй запрос ради него — лишнее ожидание."""
        await assistant_api.post(
            "/api/v1/projects",
            json=await payload(session, started_on="2020-01-01", due_on="2020-12-31"),
        )

        listed = await assistant_api.get("/api/v1/projects")

        assert listed.json()[0]["health"] == Health.RED.value

    async def test_filtering_by_colour_works_although_it_is_not_stored(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        await assistant_api.post(
            "/api/v1/projects",
            json=await payload(
                session, title="Просрочен", due_on="2020-12-31", started_on="2020-01-01"
            ),
        )
        await assistant_api.post(
            "/api/v1/projects",
            json=await payload(
                session, title="В порядке", started_on="2026-01-01", due_on="2099-12-31"
            ),
        )

        red = await assistant_api.get("/api/v1/projects", params={"health": Health.RED.value})

        assert [item["title"] for item in red.json()] == ["Просрочен"]
