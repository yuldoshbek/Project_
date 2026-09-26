"""Вымышленные данные в базе дают то, что заказчик утвердил на экранах Пульта и «Проектов».

Экран утверждали по вымышленному серверу во фронтенде, а превью показывает сервер. Если
демо в базе разойдётся с утверждённым, заказчик увидит на превью не тот экран, что
принимал, — и не поймёт, изменилось ли правило или только данные. Поэтому проверяется не
«что записано», а что из записанного насчитал сервер: ступени — сервисом показателей,
переносы — по журналу изменений.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import demo
from app.domain.attention import Attention
from app.domain.audit import AuditAction
from app.domain.clock import local_date, now_utc
from app.domain.dictionaries import OrganizationRole, ProjectStatus, TaskStatus
from app.domain.pult import MILESTONES, PROJECTS, AuditEntry, due_shift
from app.repos import attention as snapshot
from app.repos.models import (
    AuditLog,
    Milestone,
    Organization,
    Project,
    ProjectOrganization,
    Task,
)
from app.services import metrics

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")

SPECS = {spec.key: spec for spec in demo.PROJECTS}

STEPS = {
    "geodata": (Attention.AWAITING_DECISION, 2),
    "interns": (Attention.BURNING, 6),
    "air": (Attention.BLOCKED_BY_OTHERS, 25),
    "aerial": (Attention.SILENT, 21),
    "lab": (Attention.SILENT, 30),
}
"""Ступени проектов на утверждённом экране; остальные незавершённые идут по плану."""

MILESTONE_STEPS = [
    ("Согласование ТЗ на спутниковую группировку", Attention.AWAITING_DECISION, 6),
    ("Приёмка опытного образца платформы", Attention.OVERDUE, 9),
    ("Внесение стандарта в агентство «Узстандарт»", Attention.BURNING, 2),
    ("Итоги и отчёт", Attention.BURNING, 6),
    ("Получение космических снимков", Attention.BURNING, 0),
]
"""Вехи в лестнице: три из сценария Пульта, две — из шаблонов (стажировки, паводки)."""


class Loaded:
    """Демо после обеих транзакций и проекты по ключам экрана."""

    def __init__(self, now: datetime, projects: dict[str, Project]) -> None:
        self.now = now
        self.today = local_date(now, TASHKENT)
        self.projects = projects

    def on(self, days: int) -> date:
        return self.today + timedelta(days=days)

    def key_of(self, entity_id: uuid.UUID) -> str | None:
        return next((key for key, each in self.projects.items() if each.id == entity_id), None)


@pytest.fixture
async def loaded(session: AsyncSession) -> Loaded:
    now = now_utc()
    await demo.before_visit(session, now=now, zone=TASHKENT)
    await demo.after_visit(session, now=now, zone=TASHKENT)
    keys = {spec.title: spec.key for spec in demo.PROJECTS} | {demo.NEW_PROJECT: "new"}
    projects = {keys[each.title]: each for each in await session.scalars(select(Project))}
    return Loaded(now, projects)


class TestProjects:
    async def test_the_approved_projects_and_the_one_created_after_the_visit(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        assert await session.scalar(select(func.count()).select_from(Project)) == 22
        year = loaded.today.year
        for number, spec in enumerate(demo.PROJECTS, start=1):
            project = loaded.projects[spec.key]
            assert project.code == f"PRJ-{year}-{number:03d}"
            assert project.started_on == loaded.on(spec.start)
            assert project.due_on == loaded.on(spec.due)
            # Направление и регион экран называл словами; все, что есть в справочниках,
            # обязаны найтись — иначе срез по ним на превью окажется пустым.
            assert (project.direction_id is not None) is (spec.direction is not None), spec.key
            assert (project.region_id is not None) is (spec.region is not None), spec.key
        assert loaded.projects["new"].code == f"PRJ-{year}-022"

    async def test_paused_finished_and_cancelled_keep_their_reasons(self, loaded: Loaded) -> None:
        expected = {
            "snow": (ProjectStatus.ON_HOLD, SPECS["snow"].reason),
            "lab": (ProjectStatus.ON_HOLD, SPECS["lab"].reason),
            "glossary": (ProjectStatus.DONE, None),
            "hydro": (ProjectStatus.DONE, None),
            "legacy": (ProjectStatus.CANCELLED, SPECS["legacy"].reason),
        }
        for key, (status, reason) in expected.items():
            project = loaded.projects[key]
            assert (project.status_code, project.status_reason) == (status.value, reason), key
            if status.requires_reason:
                assert reason

    async def test_calibration_is_a_subproject_of_the_programme(self, loaded: Loaded) -> None:
        mission = loaded.projects["mission"]
        assert mission.is_multiyear
        assert loaded.projects["calibration"].parent_project_id == mission.id

    async def test_center_roles_and_outside_lead(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        rows = await session.execute(
            select(
                ProjectOrganization.project_id,
                ProjectOrganization.role,
                Organization.is_founded_by_agency,
            ).join(Organization, Organization.id == ProjectOrganization.organization_id)
        )
        center = set()
        outside = set()
        for project_id, role, is_center in rows:
            key = loaded.key_of(project_id)
            if is_center:
                center.add((key, role))
            elif role == OrganizationRole.LEAD_AGENCY.value:
                outside.add(key)

        assert center == {
            (spec.key, spec.center.value) for spec in demo.PROJECTS if spec.center is not None
        }
        assert outside == {"station", "air"}

    async def test_tasks_add_up_to_the_screen(self, session: AsyncSession, loaded: Loaded) -> None:
        rows = await session.execute(
            select(Task.project_id, Task.status, func.count()).group_by(
                Task.project_id, Task.status
            )
        )
        done: Counter[str | None] = Counter()
        total: Counter[str | None] = Counter()
        for project_id, status, count in rows:
            key = loaded.key_of(project_id)
            total[key] += count
            if status == TaskStatus.DONE.value:
                done[key] += count

        for spec in demo.PROJECTS:
            assert (done[spec.key], total[spec.key]) == spec.tasks, spec.key


async def later_shifts(
    session: AsyncSession, entity_type: str
) -> dict[uuid.UUID, list[tuple[date, date]]]:
    """Переносы позже по журналу — тем же правилом, что «Держим ли мы свои сроки?»."""
    rows = await session.execute(
        select(
            AuditLog.occurred_at,
            AuditLog.entity_type,
            AuditLog.entity_id,
            AuditLog.action,
            AuditLog.changes,
        ).where(
            AuditLog.entity_type == entity_type,
            AuditLog.action == AuditAction.UPDATED.value,
        )
    )
    shifts: dict[uuid.UUID, list[tuple[date, date]]] = {}
    for occurred_at, kind, entity_id, action, changes in rows:
        moved = due_shift(AuditEntry(occurred_at, kind, entity_id, action, changes), TASHKENT)
        if moved and moved[1] > moved[0]:
            shifts.setdefault(entity_id, []).append(moved)
    # Записи одной транзакции помечены одним моментом: порядок между ними не хранится,
    # сравнивается набор переносов.
    return {entity_id: sorted(moves) for entity_id, moves in shifts.items()}


class TestMoves:
    async def test_portal_and_station_moved_later_once(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        shifts = {
            loaded.key_of(entity_id): moves
            for entity_id, moves in (await later_shifts(session, PROJECTS)).items()
        }
        assert shifts == {
            "portal": [(loaded.on(30), loaded.on(60))],
            "station": [(loaded.on(61), loaded.on(75))],
        }
        for key in ("portal", "station"):
            project = loaded.projects[key]
            spec = SPECS[key]
            assert spec.original is not None
            assert project.original_due_on == loaded.on(spec.original)
            assert project.due_on == loaded.on(spec.due)

    async def test_acceptance_moved_later_twice(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        """Веха, которую продлевают хронически, — строка Пульта: с −23 через −16 к −9."""
        acceptance = await session.scalar(
            select(Milestone).where(
                Milestone.project_id == loaded.projects["portal"].id,
                Milestone.title == "Приёмка опытного образца платформы",
            )
        )
        assert acceptance is not None
        assert (acceptance.original_due_on, acceptance.due_on) == (loaded.on(-23), loaded.on(-9))
        shifts = await later_shifts(session, MILESTONES)
        assert shifts == {
            acceptance.id: [(loaded.on(-23), loaded.on(-16)), (loaded.on(-16), loaded.on(-9))]
        }


class TestLadder:
    async def test_projects_stand_on_the_approved_steps(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        ladder = await metrics.ladder(session, today=loaded.today, zone=TASHKENT)
        steps = {
            loaded.key_of(row.entity_id): (row.attention, row.deviation)
            for row in ladder.rows
            if row.section == "projects"
        }
        assert steps == STEPS

    async def test_finished_and_cancelled_are_not_in_the_ladder(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        items = await snapshot.load_items(session, zone=TASHKENT)
        in_snapshot = {loaded.key_of(item.entity_id) for item in items}
        assert {"glossary", "hydro", "legacy"}.isdisjoint(in_snapshot)
        # Пауза — не конец работы: снег в снимке есть и идёт по плану.
        assert "snow" in in_snapshot

    async def test_milestones_on_the_ladder(self, session: AsyncSession, loaded: Loaded) -> None:
        ladder = await metrics.ladder(session, today=loaded.today, zone=TASHKENT)
        marks = sorted(
            (row.title or "", row.attention, row.deviation)
            for row in ladder.rows
            if row.section == "milestones"
        )
        assert marks == sorted(MILESTONE_STEPS)
