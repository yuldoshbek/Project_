"""Программы — весь раздел одним ответом.

Форма ответа — договор экрана `frontend/src/sections/programs/model.ts`: экран утверждён
заказчиком 27.09.2026 на вымышленных данных той же формы, и API написан под него
(CLAUDE.md, цикл блока). Раздел только читает — программу правят в карточке проекта
(`app.api.routes.projects`), поэтому путь здесь один. Смотрят оба.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SettingsDep, is_demo
from app.api.security import CurrentUser
from app.api.transaction import transactional_router
from app.domain.clock import now_utc
from app.domain.dictionaries import ProjectStatus
from app.domain.programs import Pace as PaceRule
from app.domain.programs import PaceVerdict
from app.services import programs as service
from app.services.projects import PersonRef

router = transactional_router(tags=["программы"])


class Ref(BaseModel):
    id: uuid.UUID
    name: str


class TypeRef(BaseModel):
    code: str
    name: str


class Milestone(BaseModel):
    id: uuid.UUID
    title: str
    due_on: date
    original_due_on: date
    is_passed: bool
    passed_on: date | None
    days_left: int
    step: str | None
    deviation: int


class Subproject(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    status: ProjectStatus
    responsible: Ref | None
    started_on: date
    due_on: date
    original_due_on: date
    readiness: int
    step: str | None
    deviation: int
    milestones: list[Milestone]


class Pace(BaseModel):
    verdict: PaceVerdict
    window_days: int
    closed: int
    closed_tasks: int
    min_closed_tasks: int
    remaining: int
    forecast_on: date | None
    gap_days: int | None


class ProgramCard(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    type: TypeRef
    status: ProjectStatus
    responsible: Ref | None
    started_on: date
    due_on: date
    original_due_on: date
    days_left: int
    readiness: int
    lag_days: int
    step: str | None
    deviation: int
    milestones: list[Milestone]
    subprojects: list[Subproject]
    pace: Pace | None


class ProgramRef(BaseModel):
    id: uuid.UUID
    code: str
    title: str


class SubprojectRef(BaseModel):
    id: uuid.UUID
    title: str


class YearEndRow(BaseModel):
    milestone: Milestone
    program: ProgramRef
    subproject: SubprojectRef | None
    responsible: Ref | None


class Horizon(BaseModel):
    # `from` — слово языка, поэтому поле называется иначе, а в ответе — как в договоре.
    model_config = ConfigDict(populate_by_name=True)

    from_: int = Field(alias="from")
    to: int


class ProgramsResponse(BaseModel):
    as_of: datetime
    horizon: Horizon
    items: list[ProgramCard]
    year_end: list[YearEndRow]
    is_demo: bool


def _ref(person: PersonRef | None) -> Ref | None:
    return Ref(id=person.id, name=person.name) if person else None


def _milestone(mark: service.MilestoneView) -> Milestone:
    return Milestone(
        id=mark.id,
        title=mark.title,
        due_on=mark.due_on,
        original_due_on=mark.original_due_on,
        is_passed=mark.is_passed,
        passed_on=mark.passed_on,
        days_left=mark.days_left,
        step=mark.step.value if mark.step else None,
        deviation=mark.deviation,
    )


def _pace(pace: PaceRule | None) -> Pace | None:
    if pace is None:
        return None
    return Pace(
        verdict=pace.verdict,
        window_days=pace.window_days,
        closed=pace.closed,
        closed_tasks=pace.closed_tasks,
        min_closed_tasks=pace.min_closed_tasks,
        remaining=pace.remaining,
        forecast_on=pace.forecast_on,
        gap_days=pace.gap_days,
    )


def _subproject(sub: service.SubprojectView) -> Subproject:
    return Subproject(
        id=sub.id,
        code=sub.code,
        title=sub.title,
        status=ProjectStatus(sub.status),
        responsible=_ref(sub.responsible),
        started_on=sub.started_on,
        due_on=sub.due_on,
        original_due_on=sub.original_due_on,
        readiness=sub.readiness,
        step=sub.step.value if sub.step else None,
        deviation=sub.deviation,
        milestones=[_milestone(mark) for mark in sub.milestones],
    )


def _program(item: service.ProgramView) -> ProgramCard:
    return ProgramCard(
        id=item.id,
        code=item.code,
        title=item.title,
        type=TypeRef(code=item.type_code, name=item.type_name),
        status=ProjectStatus(item.status),
        responsible=_ref(item.responsible),
        started_on=item.started_on,
        due_on=item.due_on,
        original_due_on=item.original_due_on,
        days_left=item.days_left,
        readiness=item.readiness,
        lag_days=item.lag_days,
        step=item.step.value if item.step else None,
        deviation=item.deviation,
        milestones=[_milestone(mark) for mark in item.milestones],
        subprojects=[_subproject(sub) for sub in item.subprojects],
        pace=_pace(item.pace),
    )


@router.get("/programs", response_model=ProgramsResponse, summary="Программы: весь раздел")
async def read_programs(
    user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> ProgramsResponse:
    view = await service.load(
        session,
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
        locale=user.locale,
        is_demo=is_demo(settings),
    )
    first, last = view.horizon
    return ProgramsResponse(
        as_of=view.as_of,
        horizon=Horizon(from_=first, to=last),
        items=[_program(item) for item in view.items],
        year_end=[
            YearEndRow(
                milestone=_milestone(row.milestone),
                program=ProgramRef(id=row.program[0], code=row.program[1], title=row.program[2]),
                subproject=(
                    SubprojectRef(id=row.subproject[0], title=row.subproject[1])
                    if row.subproject
                    else None
                ),
                responsible=_ref(row.responsible),
            )
            for row in view.year_end
        ],
        is_demo=view.is_demo,
    )
