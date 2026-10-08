"""Read-модель раздела «Календарь»: даты всех разделов и годовые циклы.

Экран собирается одним заходом: по запросу на вид записи — сроки проектов, вехи, задачи,
решения руководителя, сроки поручений Ижро, показы докладов и мероприятий — и на каждое из
двух окон: запрошенные дни и «срок прошёл». Двести дат не стоят двухсот обращений к базе.

**Поручение Ижро — только с точным сроком** (V45). «В течение месяца» и «до конца года»
хранятся последним днём периода, и на 31.12 их сошлись бы десятки: день был бы горячим
всегда, а горячий день — сигнал, на который надо отвечать. Закрыто поручение, когда работа
уже не наша — отправлено или снято с контроля (`app.domain.ijro.OPEN_STATES`).

**Что считается закрытым.** Своё терминальное состояние — пройдена веха, готова задача,
исполнено решение, завершён проект — и завершённый проект для всего, что в нём: его вехи и
задачи больше не работа, как и в лестнице Пульта (`app.repos.attention`). Отменённое в
календаре не показывается вовсе: отменённый срок ничего не наступит.

**Даты задач — по Ташкенту.** Срок задачи хранится моментом в UTC (инвариант 8), а
календарь раскладывает по календарным дням: окно запроса переводится в моменты начала
дней по Ташкенту, а день каждой задачи — `app.domain.clock.local_date`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased

from app.domain.calendar import CalendarKind
from app.domain.clock import local_date
from app.domain.decisions import DecisionState, DecisionTarget
from app.domain.dictionaries import ProjectStatus, TaskStatus
from app.domain.ijro import OPEN_STATES, DuePrecision
from app.domain.ijro_control import task_title
from app.domain.preparations import PrepStage
from app.repos.models import (
    IjroAssignment,
    LeaderDecision,
    Milestone,
    Person,
    Preparation,
    Project,
    Task,
    YearlyCycle,
)

PROJECT_TERMINAL = [status.value for status in ProjectStatus if status.is_terminal]
TASK_TERMINAL = [status.value for status in TaskStatus if status.is_terminal]
CANCELLED_PROJECT = ProjectStatus.CANCELLED.value
DONE_PROJECT = ProjectStatus.DONE.value


@dataclass(frozen=True, slots=True)
class DatedRow:
    """Одна дата календаря из записи раздела."""

    kind: CalendarKind
    id: uuid.UUID
    on: date
    title: str | None
    decision_kind: str | None
    project_id: uuid.UUID | None
    """Чьё: проект вехи, задачи, решения; у срока проекта — он сам."""

    project_title: str | None
    responsible_id: uuid.UUID | None
    responsible_name: str | None
    is_done: bool
    about: tuple[str, uuid.UUID] | None = None
    """У решения — то, по чему оно принято: вид и номер записи."""


@dataclass(frozen=True, slots=True)
class CycleRow:
    id: uuid.UUID
    title: str
    rule: str
    month: int
    day: int
    every_years: int
    anchor_year: int
    project_id: uuid.UUID | None
    project_title: str | None
    responsible_id: uuid.UUID | None
    responsible_name: str | None
    version: int


def _start_of(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time(0), zone).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class _Window:
    """Какие даты брать: дни `[since, until]` или всё незакрытое раньше `before`."""

    since: date | None
    until: date | None
    before: date | None

    def days(
        self, column: InstrumentedAttribute[date] | InstrumentedAttribute[date | None]
    ) -> ColumnElement[bool]:
        if self.before is not None:
            return column < self.before
        return and_(column >= self.since, column <= self.until)

    def moments(
        self, column: InstrumentedAttribute[datetime | None], zone: ZoneInfo
    ) -> ColumnElement[bool]:
        if self.before is not None:
            return column < _start_of(self.before, zone)
        assert self.since is not None and self.until is not None
        return and_(
            column >= _start_of(self.since, zone),
            column < _start_of(self.until + timedelta(days=1), zone),
        )

    @property
    def open_only(self) -> bool:
        return self.before is not None


async def dated(
    session: AsyncSession, *, since: date, until: date, zone: ZoneInfo
) -> list[DatedRow]:
    """Даты с `since` по `until` включительно — закрытые тоже: календарь показывает историю."""
    return await _rows(session, _Window(since=since, until=until, before=None), zone)


async def overdue(session: AsyncSession, *, before: date, zone: ZoneInfo) -> list[DatedRow]:
    """Незакрытое со сроком раньше `before` — «срок прошёл», в каком бы месяце ни смотрели."""
    return await _rows(session, _Window(since=None, until=None, before=before), zone)


async def _rows(session: AsyncSession, window: _Window, zone: ZoneInfo) -> list[DatedRow]:
    return [
        *await _projects(session, window),
        *await _milestones(session, window),
        *await _tasks(session, window, zone),
        *await _decisions(session, window),
        *await _ijro(session, window),
        *await _preparations(session, window),
    ]


IJRO_OPEN = [state.value for state in OPEN_STATES]


async def _ijro(session: AsyncSession, window: _Window) -> list[DatedRow]:
    condition = and_(
        IjroAssignment.due_on.is_not(None),
        IjroAssignment.due_precision == DuePrecision.EXACT.value,
        window.days(IjroAssignment.due_on),
    )
    if window.open_only:
        condition = and_(condition, IjroAssignment.state.in_(IJRO_OPEN))
    rows = await session.execute(
        select(
            IjroAssignment.id,
            IjroAssignment.content,
            IjroAssignment.due_on,
            IjroAssignment.state,
            IjroAssignment.responsible_person_id,
            Person.full_name,
        )
        .outerjoin(Person, Person.id == IjroAssignment.responsible_person_id)
        .where(condition)
    )
    return [
        DatedRow(
            kind=CalendarKind.IJRO,
            id=assignment_id,
            on=due_on,
            title=task_title(content),
            decision_kind=None,
            project_id=None,
            project_title=None,
            responsible_id=responsible,
            responsible_name=name,
            is_done=state not in IJRO_OPEN,
        )
        for assignment_id, content, due_on, state, responsible, name in rows
    ]


async def _preparations(session: AsyncSession, window: _Window) -> list[DatedRow]:
    condition = window.days(Preparation.show_on)
    if window.open_only:
        condition = and_(condition, Preparation.stage != PrepStage.SHOWN.value)
    rows = await session.execute(
        select(
            Preparation.id,
            Preparation.title,
            Preparation.show_on,
            Preparation.stage,
            Project.id,
            Project.title,
            Preparation.responsible_person_id,
            Person.full_name,
        )
        .outerjoin(Project, Project.id == Preparation.project_id)
        .outerjoin(Person, Person.id == Preparation.responsible_person_id)
        .where(condition)
    )
    return [
        DatedRow(
            kind=CalendarKind.PREPARATION,
            id=preparation_id,
            on=show_on,
            title=title,
            decision_kind=None,
            project_id=project_id,
            project_title=project_title,
            responsible_id=responsible,
            responsible_name=name,
            is_done=stage == PrepStage.SHOWN.value,
        )
        for (
            preparation_id,
            title,
            show_on,
            stage,
            project_id,
            project_title,
            responsible,
            name,
        ) in rows
    ]


async def _projects(session: AsyncSession, window: _Window) -> list[DatedRow]:
    condition = and_(Project.status_code != CANCELLED_PROJECT, window.days(Project.due_on))
    if window.open_only:
        condition = and_(condition, Project.status_code.notin_(PROJECT_TERMINAL))
    rows = await session.execute(
        select(
            Project.id,
            Project.title,
            Project.due_on,
            Project.status_code,
            Project.responsible_person_id,
            Person.full_name,
        )
        .outerjoin(Person, Person.id == Project.responsible_person_id)
        .where(condition)
    )
    return [
        DatedRow(
            kind=CalendarKind.PROJECT,
            id=project_id,
            on=due_on,
            title=title,
            decision_kind=None,
            project_id=project_id,
            project_title=title,
            responsible_id=responsible,
            responsible_name=name,
            is_done=status == DONE_PROJECT,
        )
        for project_id, title, due_on, status, responsible, name in rows
    ]


async def _milestones(session: AsyncSession, window: _Window) -> list[DatedRow]:
    condition = and_(Project.status_code != CANCELLED_PROJECT, window.days(Milestone.due_on))
    if window.open_only:
        condition = and_(
            condition,
            Milestone.is_passed.is_(False),
            Project.status_code.notin_(PROJECT_TERMINAL),
        )
    rows = await session.execute(
        select(
            Milestone.id,
            Milestone.title,
            Milestone.due_on,
            Milestone.is_passed,
            Project.id,
            Project.title,
            Project.status_code,
            Project.responsible_person_id,
            Person.full_name,
        )
        .join(Project, Project.id == Milestone.project_id)
        .outerjoin(Person, Person.id == Project.responsible_person_id)
        .where(condition)
        .order_by(Milestone.due_on, Milestone.sort_order)
    )
    return [
        DatedRow(
            kind=CalendarKind.MILESTONE,
            id=milestone_id,
            on=due_on,
            title=title,
            decision_kind=None,
            project_id=project_id,
            project_title=project_title,
            # Ответственный за веху — ответственный проекта: у вехи своего нет (ТЗ 3.1).
            responsible_id=responsible,
            responsible_name=name,
            is_done=passed or status == DONE_PROJECT,
        )
        for (
            milestone_id,
            title,
            due_on,
            passed,
            project_id,
            project_title,
            status,
            responsible,
            name,
        ) in rows
    ]


async def _tasks(session: AsyncSession, window: _Window, zone: ZoneInfo) -> list[DatedRow]:
    condition = and_(
        Task.due_at.is_not(None),
        Task.status != TaskStatus.CANCELLED.value,
        or_(Task.project_id.is_(None), Project.status_code != CANCELLED_PROJECT),
        window.moments(Task.due_at, zone),
    )
    if window.open_only:
        condition = and_(
            condition,
            Task.status.notin_(TASK_TERMINAL),
            or_(Task.project_id.is_(None), Project.status_code.notin_(PROJECT_TERMINAL)),
        )
    rows = await session.execute(
        select(
            Task.id,
            Task.title,
            Task.due_at,
            Task.status,
            Project.id,
            Project.title,
            Project.status_code,
            Task.assignee_person_id,
            Person.full_name,
        )
        .outerjoin(Project, Project.id == Task.project_id)
        .outerjoin(Person, Person.id == Task.assignee_person_id)
        .where(condition)
    )
    return [
        DatedRow(
            kind=CalendarKind.TASK,
            id=task_id,
            on=local_date(due_at, zone),
            title=title,
            decision_kind=None,
            project_id=project_id,
            project_title=project_title,
            responsible_id=assignee,
            responsible_name=name,
            is_done=status == TaskStatus.DONE.value or project_status == DONE_PROJECT,
        )
        for (
            task_id,
            title,
            due_at,
            status,
            project_id,
            project_title,
            project_status,
            assignee,
            name,
        ) in rows
    ]


async def _decisions(session: AsyncSession, window: _Window) -> list[DatedRow]:
    """Сроки исполнения решений руководителя. Чьё — проект того, по чему решение."""
    mark = aliased(Milestone)
    work = aliased(Task)
    owner = case(
        (LeaderDecision.target_type == DecisionTarget.PROJECT.value, LeaderDecision.target_id),
        (LeaderDecision.target_type == DecisionTarget.MILESTONE.value, mark.project_id),
        (LeaderDecision.target_type == DecisionTarget.TASK.value, work.project_id),
        else_=None,
    )
    condition = and_(LeaderDecision.due_on.is_not(None), window.days(LeaderDecision.due_on))
    if window.open_only:
        condition = and_(condition, LeaderDecision.state == DecisionState.OPEN.value)
    rows = await session.execute(
        select(
            LeaderDecision.id,
            LeaderDecision.text,
            LeaderDecision.kind,
            LeaderDecision.due_on,
            LeaderDecision.state,
            Project.id,
            Project.title,
            LeaderDecision.assignee_person_id,
            Person.full_name,
            LeaderDecision.target_type,
            LeaderDecision.target_id,
        )
        .outerjoin(
            mark,
            and_(
                LeaderDecision.target_type == DecisionTarget.MILESTONE.value,
                mark.id == LeaderDecision.target_id,
            ),
        )
        .outerjoin(
            work,
            and_(
                LeaderDecision.target_type == DecisionTarget.TASK.value,
                work.id == LeaderDecision.target_id,
            ),
        )
        .outerjoin(Project, Project.id == owner)
        .outerjoin(Person, Person.id == LeaderDecision.assignee_person_id)
        .where(condition)
    )
    return [
        DatedRow(
            kind=CalendarKind.DECISION,
            id=decision_id,
            on=due_on,
            title=text,
            decision_kind=kind,
            project_id=project_id,
            project_title=project_title,
            responsible_id=assignee,
            responsible_name=name,
            is_done=state == DecisionState.DONE.value,
            about=(target_type, target_id),
        )
        for (
            decision_id,
            text,
            kind,
            due_on,
            state,
            project_id,
            project_title,
            assignee,
            name,
            target_type,
            target_id,
        ) in rows
    ]


def _cycle_select(condition: ColumnElement[bool]) -> Any:
    return (
        select(
            YearlyCycle.id,
            YearlyCycle.title,
            YearlyCycle.rule,
            YearlyCycle.month,
            YearlyCycle.day,
            YearlyCycle.every_years,
            YearlyCycle.anchor_year,
            Project.id,
            Project.title,
            YearlyCycle.responsible_person_id,
            Person.full_name,
            YearlyCycle.version,
        )
        .outerjoin(Project, Project.id == YearlyCycle.project_id)
        .outerjoin(Person, Person.id == YearlyCycle.responsible_person_id)
        .where(condition)
        .order_by(YearlyCycle.title)
    )


async def cycles(session: AsyncSession) -> list[CycleRow]:
    """Действующие годовые циклы — отменённые в календаре не показываются."""
    rows = await session.execute(_cycle_select(YearlyCycle.is_active.is_(True)))
    return [CycleRow(*row) for row in rows]


async def cycle(session: AsyncSession, cycle_id: uuid.UUID) -> CycleRow | None:
    """Действующий цикл по номеру; отменённый — как отсутствующий."""
    rows = await session.execute(
        _cycle_select(and_(YearlyCycle.id == cycle_id, YearlyCycle.is_active.is_(True)))
    )
    found = rows.first()
    return CycleRow(*found) if found is not None else None
