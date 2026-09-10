"""Проекты: чтение и изменение.

Цвет светофора приходит вместе с проектом, а не отдельным запросом: список без него
бесполезен, а два обращения ради одного экрана — лишнее ожидание там, где норматив ТЗ
10.2 отводит на весь дашборд 400 мс.

Читать может любой вошедший, изменять — только помощник. Руководителю на запись доступно
ровно одно действие, решение по проекту на контроле, и оно заводится своим тикетом
(ORB-062): исключение должно быть видно в коде, а не спрятано в послаблении охранника
([ADR-0011](../../../docs/adr/ADR-0011-two-user-scope.md)).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SettingsDep
from app.api.security import Assistant, get_active_user
from app.domain.clock import today_in
from app.domain.dictionaries import Health
from app.domain.projects import Classification, ProgressMode, ProjectKind
from app.services import projects as service

router = APIRouter(tags=["проекты"], dependencies=[Depends(get_active_user)])

TITLE_MAX = 300


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    title: str
    description: str | None
    kind: ProjectKind
    classification: Classification
    direction_id: uuid.UUID
    curator_person_id: uuid.UUID | None
    status_code: str
    status_reason: str | None
    priority_code: str
    started_on: date
    due_on: date
    finished_on: date | None
    progress_pct: int
    progress_mode: ProgressMode
    budget_note: str | None
    health: Health

    @classmethod
    def of(cls, project: Any, health: Health) -> ProjectResponse:
        return cls(
            **{name: getattr(project, name) for name in cls.model_fields if name != "health"},
            health=health,
        )


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    direction_id: uuid.UUID
    status_code: str
    priority_code: str
    started_on: date
    due_on: date
    kind: ProjectKind = ProjectKind.PROJECT
    classification: Classification = Classification.INTERNAL
    description: str | None = None
    curator_person_id: uuid.UUID | None = None
    status_reason: str | None = None
    finished_on: date | None = None
    progress_pct: int = 0
    progress_mode: ProgressMode = ProgressMode.AUTO
    budget_note: str | None = None


class ProjectUpdate(BaseModel):
    """Частичное изменение.

    Непереданное поле остаётся как было; переданное `null` — обнуляется. Различить их
    без `model_fields_set` невозможно, и тогда любое изменение стирало бы причину
    приостановки молча.
    """

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    description: str | None = None
    kind: ProjectKind | None = None
    classification: Classification | None = None
    direction_id: uuid.UUID | None = None
    curator_person_id: uuid.UUID | None = None
    status_code: str | None = None
    status_reason: str | None = None
    priority_code: str | None = None
    started_on: date | None = None
    due_on: date | None = None
    finished_on: date | None = None
    progress_pct: int | None = None
    progress_mode: ProgressMode | None = None
    budget_note: str | None = None

    def to_patch(self) -> service.ProjectPatch:
        return service.ProjectPatch(**{name: getattr(self, name) for name in self.model_fields_set})


@router.get("/projects", response_model=list[ProjectResponse], summary="Портфель проектов")
async def list_projects(
    session: SessionDep,
    settings: SettingsDep,
    direction_id: Annotated[uuid.UUID | None, Query()] = None,
    status_code: Annotated[str | None, Query()] = None,
    priority_code: Annotated[str | None, Query()] = None,
    kind: Annotated[ProjectKind | None, Query()] = None,
    classification: Annotated[Classification | None, Query()] = None,
    curator_person_id: Annotated[uuid.UUID | None, Query()] = None,
    search: Annotated[str | None, Query(description="Совпадение по части названия")] = None,
    health: Annotated[Health | None, Query(description="Цвет светофора")] = None,
    organization_id: Annotated[
        uuid.UUID | None, Query(description="Проекты этого партнёра")
    ] = None,
    partner_search: Annotated[
        str | None, Query(description="Проекты партнёра по части его названия")
    ] = None,
    sort_by: Annotated[
        str, Query(description=f"Одно из: {', '.join(service.SORTABLE)}")
    ] = "due_on",
    descending: Annotated[bool, Query()] = False,
) -> list[ProjectResponse]:
    rows = await service.list_projects(
        session,
        service.ProjectFilter(
            direction_id=direction_id,
            status_code=status_code,
            priority_code=priority_code,
            kind=kind,
            classification=classification,
            curator_person_id=curator_person_id,
            search=search,
            health=health,
            organization_id=organization_id,
            partner_search=partner_search,
        ),
        today=today_in(settings.timezone),
        sort_by=sort_by,
        descending=descending,
    )
    return [ProjectResponse.of(project, colour) for project, colour in rows]


@router.post("/projects", response_model=ProjectResponse, status_code=201, summary="Новый проект")
async def create_project(
    payload: ProjectCreate, session: SessionDep, settings: SettingsDep, user: Assistant
) -> ProjectResponse:
    today = today_in(settings.timezone)
    project = await service.create(
        session,
        service.ProjectDraft(**payload.model_dump()),
        created_by=user.id,
        today=today,
    )
    rules = await service.load_health_rules(session)
    return ProjectResponse.of(project, rules.of(project, today=today))


@router.get("/projects/{project_id}", response_model=ProjectResponse, summary="Карточка проекта")
async def read_project(
    project_id: uuid.UUID, session: SessionDep, settings: SettingsDep
) -> ProjectResponse:
    project = await service.get(session, project_id)
    rules = await service.load_health_rules(session)
    return ProjectResponse.of(project, rules.of(project, today=today_in(settings.timezone)))


@router.patch("/projects/{project_id}", response_model=ProjectResponse, summary="Изменение проекта")
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    session: SessionDep,
    settings: SettingsDep,
    user: Assistant,
) -> ProjectResponse:
    project = await service.update(session, project_id, payload.to_patch())
    rules = await service.load_health_rules(session)
    return ProjectResponse.of(project, rules.of(project, today=today_in(settings.timezone)))


@router.delete("/projects/{project_id}", status_code=204, summary="Удаление проекта")
async def delete_project(project_id: uuid.UUID, session: SessionDep, user: Assistant) -> None:
    """Полное удаление.

    Обычный способ убрать проект с глаз — архив (ORB-025), а не удаление: завершённая
    работа остаётся историей агентства. Удаление нужно для заведённого по ошибке.
    """
    await service.delete(session, project_id)
