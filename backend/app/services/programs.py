"""Программы — сборка раздела (ТЗ 2, 5; блок 1).

Форма — договор экрана `frontend/src/sections/programs/model.ts`, утверждённого заказчиком
27.09.2026 на вымышленных данных той же формы (CLAUDE.md, цикл блока «экран → API»).

Раздел только читает: программу правят в карточке проекта. Поэтому здесь нет ни правок,
ни версий — одна read-модель на весь экран.

**Числа — из `app.services.metrics`** (инвариант 2): ступени программ, подпроектов и вех —
строки той же лестницы, что у Пульта; готовность и отставание — `metrics.progress` по тому
же набору работ, что у карточки программы в «Проектах» (`metrics.work_of`, V13); отсчёт и
«успеваем?» — `metrics.countdown` и `metrics.pace`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import Attention, Ladder, Row
from app.domain.clock import local_date
from app.domain.dictionaries import ProjectStatus, localized_name
from app.domain.programs import Pace, horizon, year_end
from app.repos import programs as programs_model
from app.repos import projects as read_model
from app.repos.projects import MarkRow, ProjectRow
from app.services import metrics
from app.services.projects import MILESTONES, PROJECTS, PersonRef, children_of, ordered

Key = tuple[str, uuid.UUID]


@dataclass(frozen=True, slots=True)
class MilestoneView:
    id: uuid.UUID
    title: str
    due_on: date
    original_due_on: date
    is_passed: bool
    passed_on: date | None
    days_left: int
    step: Attention | None
    deviation: int


@dataclass(frozen=True, slots=True)
class SubprojectView:
    id: uuid.UUID
    code: str
    title: str
    status: str
    responsible: PersonRef | None
    started_on: date
    due_on: date
    original_due_on: date
    readiness: int
    step: Attention | None
    deviation: int
    milestones: list[MilestoneView]


@dataclass(frozen=True, slots=True)
class ProgramView:
    id: uuid.UUID
    code: str
    title: str
    type_code: str
    type_name: str
    status: str
    responsible: PersonRef | None
    started_on: date
    due_on: date
    original_due_on: date
    days_left: int
    readiness: int
    lag_days: int
    step: Attention | None
    deviation: int
    milestones: list[MilestoneView]
    subprojects: list[SubprojectView]
    pace: Pace | None


@dataclass(frozen=True, slots=True)
class YearEndView:
    milestone: MilestoneView
    program: tuple[uuid.UUID, str, str]
    """Идентификатор, номер и название программы."""

    subproject: tuple[uuid.UUID, str] | None
    responsible: PersonRef | None


@dataclass(frozen=True, slots=True)
class ProgramsView:
    as_of: datetime
    horizon: tuple[int, int]
    items: list[ProgramView]
    year_end: list[YearEndView]
    is_demo: bool


@dataclass(frozen=True, slots=True)
class _Context:
    today: date
    locale: str
    steps: dict[Key, Row]


def _person(row: ProjectRow) -> PersonRef | None:
    if row.responsible_id and row.responsible_name:
        return PersonRef(id=row.responsible_id, name=row.responsible_name)
    return None


def _step(context: _Context, key: Key) -> tuple[Attention | None, int]:
    found = context.steps.get(key)
    return (found.attention, found.deviation) if found else (None, 0)


def _milestones(marks: list[MarkRow], context: _Context) -> list[MilestoneView]:
    # По сроку, а не по порядку вех проекта: экран спрашивает, что и когда наступит, и
    # «далее» у программы — ближайшая непройденная веха.
    views = []
    for mark in sorted(marks, key=lambda each: (each.due_on, each.title)):
        step, deviation = _step(context, (MILESTONES, mark.id))
        views.append(
            MilestoneView(
                id=mark.id,
                title=mark.title,
                due_on=mark.due_on,
                original_due_on=mark.original_due_on,
                is_passed=mark.is_passed,
                passed_on=mark.passed_on,
                days_left=metrics.countdown(due_on=mark.due_on, today=context.today),
                step=step,
                deviation=deviation,
            )
        )
    return views


def _subproject(row: ProjectRow, context: _Context) -> SubprojectView:
    figures = metrics.progress(
        status=ProjectStatus(row.status),
        started_on=row.started_on,
        due_on=row.due_on,
        today=context.today,
        work=metrics.work_of(row),
    )
    step, deviation = _step(context, (PROJECTS, row.id))
    return SubprojectView(
        id=row.id,
        code=row.code,
        title=row.title,
        status=row.status,
        responsible=_person(row),
        started_on=row.started_on,
        due_on=row.due_on,
        original_due_on=row.original_due_on,
        readiness=figures.readiness,
        step=step,
        deviation=deviation,
        milestones=_milestones(row.marks, context),
    )


def _program(
    row: ProjectRow,
    children: list[ProjectRow],
    closed_tasks: dict[uuid.UUID, int],
    context: _Context,
    thresholds: metrics.Thresholds,
    ladder: Ladder,
) -> ProgramView:
    figures = metrics.progress(
        status=ProjectStatus(row.status),
        started_on=row.started_on,
        due_on=row.due_on,
        today=context.today,
        work=metrics.work_of(row, children),
    )
    pace = metrics.program_pace(
        row, children, closed_tasks=closed_tasks, today=context.today, thresholds=thresholds
    )
    step, deviation = _step(context, (PROJECTS, row.id))
    return ProgramView(
        id=row.id,
        code=row.code,
        title=row.title,
        type_code=row.type_code,
        type_name=localized_name(
            context.locale,
            ru=row.type_names.ru,
            uz_cyrl=row.type_names.uz_cyrl,
            uz_latn=row.type_names.uz_latn,
        ),
        status=row.status,
        responsible=_person(row),
        started_on=row.started_on,
        due_on=row.due_on,
        original_due_on=row.original_due_on,
        days_left=metrics.countdown(due_on=row.due_on, today=context.today),
        readiness=figures.readiness,
        lag_days=figures.lag_days,
        step=step,
        deviation=deviation,
        milestones=_milestones(row.marks, context),
        subprojects=ordered([_subproject(child, context) for child in children], ladder),
        pace=pace,
    )


def _year_end(items: list[ProgramView], today: date) -> list[YearEndView]:
    """Непройденные вехи программ и подпроектов до 31 декабря — просроченные первыми.

    Просроченная веха стоит в начале по сроку сама: она не случилась и всё ещё должна
    случиться в этом году. Закрытость проверяется у владельца вехи: у закрытой программы
    может идти незакрытый подпроект, и его просроченная веха стоит на Пульте — пропасть
    отсюда она не должна.
    """
    last = year_end(today)
    rows: list[YearEndView] = []
    for program in items:
        ref = (program.id, program.code, program.title)
        if not ProjectStatus(program.status).is_terminal:
            rows.extend(
                YearEndView(
                    milestone=mark, program=ref, subproject=None, responsible=program.responsible
                )
                for mark in program.milestones
                if not mark.is_passed and mark.due_on <= last
            )
        for sub in program.subprojects:
            if ProjectStatus(sub.status).is_terminal:
                continue
            rows.extend(
                YearEndView(
                    milestone=mark,
                    program=ref,
                    subproject=(sub.id, sub.title),
                    responsible=sub.responsible,
                )
                for mark in sub.milestones
                if not mark.is_passed and mark.due_on <= last
            )
    # До конца — однозначно: при равных сроке и названии порядок не должен меняться от
    # запроса к запросу.
    return sorted(
        rows,
        key=lambda row: (
            row.milestone.due_on,
            row.milestone.title,
            row.program[1],
            row.subproject[1] if row.subproject else "",
            str(row.milestone.id),
        ),
    )


async def load(
    session: AsyncSession, *, now: datetime, zone: ZoneInfo, locale: str, is_demo: bool
) -> ProgramsView:
    """Весь раздел одним запросом: программы с вехами и подпроектами, «до конца года»."""
    today = local_date(now, zone)
    thresholds = await metrics.load_thresholds(session)
    ladder = await metrics.ladder(session, today=today, zone=zone, thresholds=thresholds)
    context = _Context(
        today=today,
        locale=locale,
        steps={(row.section, row.entity_id): row for row in ladder.rows},
    )

    ids = await programs_model.scope(session)
    rows = await read_model.projects(session, ids=ids) if ids else []
    since, until = metrics.pace_window(today, zone)
    closed_tasks = await programs_model.closed_tasks_between(session, ids, since, until)

    children = children_of(rows)
    items = [
        _program(row, children.get(row.id, []), closed_tasks, context, thresholds, ladder)
        for row in rows
        if row.is_multiyear
    ]
    items = ordered(items, ladder)
    return ProgramsView(
        as_of=now,
        horizon=horizon(today),
        items=items,
        year_end=_year_end(items, today),
        is_demo=is_demo,
    )
