"""Проекты — раздел целиком, карточка, новый проект, статус, «что мешает», «что если».

Форма ответа — договор экрана `frontend/src/sections/projects/model.ts`: экран утверждён
заказчиком 25.09.2026 на вымышленных данных той же формы, и API написан под него, а не
наоборот (CLAUDE.md, цикл блока). Эндпоинта, которому нет места на экране, здесь нет.

Смотрят оба, вносит помощник (`Assistant`): руководитель открывает систему, чтобы видеть и
решать. «Что если» — исключение по смыслу, а не по правам: он ничего не записывает, и
считать его может и руководитель.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import status
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, SettingsDep, is_demo
from app.api.security import Assistant, CurrentUser
from app.api.transaction import transactional_router
from app.domain.clock import local_date, now_utc
from app.domain.dictionaries import OrganizationRole, ProjectStatus
from app.domain.projects import IMPEDIMENT_MAX_LENGTH, TITLE_MAX_LENGTH
from app.services import projects as service

router = transactional_router(tags=["проекты"])


class Ref(BaseModel):
    id: uuid.UUID
    name: str


class TypeRef(BaseModel):
    code: str
    name: str


class ParentRef(BaseModel):
    id: uuid.UUID
    title: str


class Impediment(BaseModel):
    text: str
    updated_on: date
    stale: bool


class NextMilestone(BaseModel):
    title: str
    due_on: date


class Mark(BaseModel):
    title: str
    due_on: date
    is_passed: bool


class Passed(BaseModel):
    passed: int
    total: int


class Done(BaseModel):
    done: int
    total: int


class ProjectCard(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    type: TypeRef
    status: ProjectStatus
    status_reason: str | None
    parent: ParentRef | None
    is_multiyear: bool
    subprojects: int
    started_on: date
    due_on: date
    original_due_on: date
    moves: int
    responsible: Ref | None
    readiness: int
    lag_days: int
    step: str | None
    deviation: int
    impediment: Impediment | None
    lead_outside: bool
    center_role: OrganizationRole | None
    next_milestone: NextMilestone | None
    milestones: Passed
    tasks: Done
    marks: list[Mark]
    version: int


class TemplateStep(BaseModel):
    title: str
    offset_days: int


class ProjectType(BaseModel):
    code: str
    name: str
    template: list[TemplateStep]


class ProjectsResponse(BaseModel):
    as_of: datetime
    items: list[ProjectCard]
    types: list[ProjectType]
    people: list[Ref]
    is_demo: bool


class Organization(BaseModel):
    id: uuid.UUID
    name: str
    role: OrganizationRole
    is_center: bool


class MilestoneRow(BaseModel):
    id: uuid.UUID
    title: str
    due_on: date
    original_due_on: date
    is_passed: bool
    passed_on: date | None
    step: str | None
    deviation: int
    version: int


class TaskRow(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    due_on: date | None
    assignee: Ref | None
    step: str | None


class Question(BaseModel):
    text: str
    asked_on: date


class LastDecision(BaseModel):
    kind: str
    decided_on: date


class ProjectDetail(ProjectCard):
    description: str | None
    direction: str | None
    region: str | None
    organizations: list[Organization]
    milestone_list: list[MilestoneRow]
    subproject_list: list[ProjectCard]
    task_list: list[TaskRow]
    question: Question | None
    last_decision: LastDecision | None


def _card(card: service.CardView) -> ProjectCard:
    return ProjectCard(**_card_fields(card))


def _card_fields(card: service.CardView) -> dict[str, object]:
    return {
        "id": card.id,
        "code": card.code,
        "title": card.title,
        "type": TypeRef(code=card.type_code, name=card.type_name),
        "status": ProjectStatus(card.status),
        "status_reason": card.status_reason,
        "parent": ParentRef(id=card.parent[0], title=card.parent[1]) if card.parent else None,
        "is_multiyear": card.is_multiyear,
        "subprojects": card.subprojects,
        "started_on": card.started_on,
        "due_on": card.due_on,
        "original_due_on": card.original_due_on,
        "moves": card.moves,
        "responsible": (
            Ref(id=card.responsible.id, name=card.responsible.name) if card.responsible else None
        ),
        "readiness": card.readiness,
        "lag_days": card.lag_days,
        "step": card.step.value if card.step else None,
        "deviation": card.deviation,
        "impediment": (
            Impediment(
                text=card.impediment.text,
                updated_on=card.impediment.updated_on,
                stale=card.impediment.stale,
            )
            if card.impediment
            else None
        ),
        "lead_outside": card.lead_outside,
        "center_role": OrganizationRole(card.center_role) if card.center_role else None,
        "next_milestone": (
            NextMilestone(title=card.next_milestone.title, due_on=card.next_milestone.due_on)
            if card.next_milestone
            else None
        ),
        "milestones": Passed(passed=card.milestones_passed, total=card.milestones_total),
        "tasks": Done(done=card.tasks_done, total=card.tasks_total),
        "marks": [
            Mark(title=mark.title, due_on=mark.due_on, is_passed=mark.is_passed)
            for mark in card.marks
        ],
        "version": card.version,
    }


def _detail(view: service.DetailView) -> ProjectDetail:
    return ProjectDetail(
        **_card_fields(view.card),
        description=view.description,
        direction=view.direction,
        region=view.region,
        organizations=[
            Organization(
                id=org.id, name=org.name, role=OrganizationRole(org.role), is_center=org.is_center
            )
            for org in view.organizations
        ],
        milestone_list=[
            MilestoneRow(
                id=mark.id,
                title=mark.title,
                due_on=mark.due_on,
                original_due_on=mark.original_due_on,
                is_passed=mark.is_passed,
                passed_on=mark.passed_on,
                step=mark.step.value if mark.step else None,
                deviation=mark.deviation,
                version=mark.version,
            )
            for mark in view.milestones
        ],
        subproject_list=[_card(sub) for sub in view.subprojects],
        task_list=[
            TaskRow(
                id=task.id,
                title=task.title,
                status=task.status,
                due_on=task.due_on,
                assignee=Ref(id=task.assignee.id, name=task.assignee.name)
                if task.assignee
                else None,
                step=task.step.value if task.step else None,
            )
            for task in view.tasks
        ],
        question=Question(text=view.question[0], asked_on=view.question[1])
        if view.question
        else None,
        last_decision=LastDecision(kind=view.last_decision[0], decided_on=view.last_decision[1])
        if view.last_decision
        else None,
    )


@router.get("/projects", response_model=ProjectsResponse, summary="Проекты: весь раздел")
async def read_projects(
    user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> ProjectsResponse:
    view = await service.load(
        session,
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
        locale=user.locale,
        is_demo=is_demo(settings),
    )
    return ProjectsResponse(
        as_of=view.as_of,
        items=[_card(card) for card in view.items],
        types=[
            ProjectType(
                code=kind.code,
                name=kind.name,
                template=[
                    TemplateStep(title=title, offset_days=offset) for title, offset in kind.template
                ],
            )
            for kind in view.types
        ],
        people=[Ref(id=person.id, name=person.name) for person in view.people],
        is_demo=view.is_demo,
    )


@router.get("/projects/{project_id}", response_model=ProjectDetail, summary="Карточка проекта")
async def read_project(
    project_id: uuid.UUID, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> ProjectDetail:
    view = await service.detail(
        session,
        project_id=project_id,
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
        locale=user.locale,
    )
    return _detail(view)


class NewProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    type_code: str = Field(min_length=1, max_length=50)
    started_on: date
    due_on: date | None = None
    responsible_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    is_multiyear: bool = False


@router.post(
    "/projects",
    response_model=ProjectDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Новый проект: название и тип, вехи из шаблона",
)
async def create_project(
    body: NewProjectRequest, user: Assistant, session: SessionDep, settings: SettingsDep
) -> ProjectDetail:
    zone = ZoneInfo(settings.timezone)
    now = now_utc()
    project_id = await service.create(
        session,
        user=user,
        data=service.NewProject(
            title=body.title,
            type_code=body.type_code,
            started_on=body.started_on,
            due_on=body.due_on,
            responsible_id=body.responsible_id,
            parent_id=body.parent_id,
            is_multiyear=body.is_multiyear,
        ),
        today=local_date(now, zone),
        locale=user.locale,
    )
    return _detail(
        await service.detail(session, project_id=project_id, now=now, zone=zone, locale=user.locale)
    )


class StatusRequest(BaseModel):
    status: ProjectStatus
    reason: str | None = Field(default=None, max_length=IMPEDIMENT_MAX_LENGTH)
    version: int


@router.put(
    "/projects/{project_id}/status",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Статус проекта; пауза и отмена — с причиной",
)
async def update_status(
    project_id: uuid.UUID, body: StatusRequest, user: Assistant, session: SessionDep
) -> None:
    await service.set_status(
        session,
        project_id=project_id,
        status=body.status,
        reason=body.reason,
        version=body.version,
    )


class ImpedimentRequest(BaseModel):
    text: str = Field(max_length=IMPEDIMENT_MAX_LENGTH)
    version: int


@router.put(
    "/projects/{project_id}/impediment",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="«Что мешает»: одна строка; пустая — помеху сняли",
)
async def update_impediment(
    project_id: uuid.UUID, body: ImpedimentRequest, user: Assistant, session: SessionDep
) -> None:
    await service.set_impediment(
        session, project_id=project_id, text=body.text, version=body.version, now=now_utc()
    )


class WhatIfChange(BaseModel):
    kind: Literal["project", "milestone"]
    id: uuid.UUID
    due_on: date


class WhatIfRequest(BaseModel):
    changes: list[WhatIfChange] = Field(max_length=service.MAX_CHANGES)


class WhatIfState(BaseModel):
    step: str | None
    deviation: int
    lag_days: int
    due_on: date


class ProjectShift(BaseModel):
    before: WhatIfState
    after: WhatIfState


class MilestoneShift(BaseModel):
    id: uuid.UUID
    title: str
    before: str | None
    after: str | None


class PultShift(BaseModel):
    before: dict[str, int]
    after: dict[str, int]


class WhatIfResponse(BaseModel):
    project: ProjectShift
    milestones: list[MilestoneShift]
    pult: PultShift


def _state(state: service.StateView) -> WhatIfState:
    return WhatIfState(
        step=state.step.value if state.step else None,
        deviation=state.deviation,
        lag_days=state.lag_days,
        due_on=state.due_on,
    )


@router.post(
    "/projects/{project_id}/what-if",
    response_model=WhatIfResponse,
    summary="«Что если»: другие сроки — расчёт без записи",
)
async def what_if(
    project_id: uuid.UUID,
    body: WhatIfRequest,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> WhatIfResponse:
    view = await service.what_if(
        session,
        project_id=project_id,
        changes=[
            service.DueChange(
                kind=service.ChangeKind(change.kind), id=change.id, due_on=change.due_on
            )
            for change in body.changes
        ],
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
    )
    return WhatIfResponse(
        project=ProjectShift(before=_state(view.before), after=_state(view.after)),
        milestones=[
            MilestoneShift(
                id=shift.id,
                title=shift.title,
                before=shift.before.value if shift.before else None,
                after=shift.after.value if shift.after else None,
            )
            for shift in view.milestones
        ],
        pult=PultShift(before=view.pult_before, after=view.pult_after),
    )


class DatesChange(WhatIfChange):
    version: int


class DatesRequest(BaseModel):
    changes: list[DatesChange] = Field(max_length=service.MAX_CHANGES)


@router.put(
    "/projects/{project_id}/dates",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Применить «что если»: записать новые сроки проекта и вех",
)
async def update_dates(
    project_id: uuid.UUID, body: DatesRequest, user: Assistant, session: SessionDep
) -> None:
    await service.apply_dates(
        session,
        project_id=project_id,
        changes=[
            service.DueChange(
                kind=service.ChangeKind(change.kind),
                id=change.id,
                due_on=change.due_on,
                version=change.version,
            )
            for change in body.changes
        ],
    )
