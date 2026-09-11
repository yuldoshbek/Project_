"""Вехи проекта.

`missed` в ответе есть, а в базе его нет: пропущенность — следствие наступившего срока,
а не решение человека (`app.domain.milestones`).

Проверки «мини-проекту нельзя вехи» здесь нет намеренно. Мини-проект вех **не требует** —
это разные вещи: запрет заставил бы менять вид проекта ради одной контрольной точки.
Раздел вех у мини-проекта не показывается, и это решение интерфейса (ORB-018), а не API.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SettingsDep
from app.api.security import Assistant, get_active_user
from app.api.transaction import transactional_router
from app.domain.clock import today_in
from app.domain.milestones import MilestoneState, MilestoneStatus
from app.services import milestones as service

router = transactional_router(tags=["вехи"], dependencies=[Depends(get_active_user)])

TITLE_MAX = 300


class MilestoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    due_on: date
    state: MilestoneState
    status: MilestoneStatus
    sort_order: int

    @classmethod
    def of(cls, item: service.MilestoneView) -> MilestoneResponse:
        stored = {
            name: getattr(item.milestone, name) for name in cls.model_fields if name != "status"
        }
        return cls(**stored, status=item.status)


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    due_on: date
    description: str | None = None
    state: MilestoneState = MilestoneState.PLANNED


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    description: str | None = None
    due_on: date | None = None
    state: MilestoneState | None = None

    def to_patch(self) -> service.MilestonePatch:
        return service.MilestonePatch(
            **{name: getattr(self, name) for name in self.model_fields_set}
        )


class MilestoneOrder(BaseModel):
    """Весь порядок целиком, а не перестановка одной вехи."""

    milestone_ids: Annotated[list[uuid.UUID], Field(min_length=1)]


@router.get(
    "/projects/{project_id}/milestones",
    response_model=list[MilestoneResponse],
    summary="Вехи проекта",
)
async def list_milestones(
    project_id: uuid.UUID, session: SessionDep, settings: SettingsDep
) -> list[MilestoneResponse]:
    rows = await service.list_for_project(session, project_id, today=today_in(settings.timezone))
    return [MilestoneResponse.of(item) for item in rows]


@router.post(
    "/projects/{project_id}/milestones",
    response_model=MilestoneResponse,
    status_code=201,
    summary="Новая веха",
)
async def create_milestone(
    project_id: uuid.UUID,
    payload: MilestoneCreate,
    session: SessionDep,
    settings: SettingsDep,
    user: Assistant,
) -> MilestoneResponse:
    milestone = await service.create(
        session, project_id, service.MilestoneDraft(**payload.model_dump())
    )
    return MilestoneResponse.of(service.view(milestone, today=today_in(settings.timezone)))


@router.put(
    "/projects/{project_id}/milestones/order",
    response_model=list[MilestoneResponse],
    summary="Порядок вех",
)
async def reorder_milestones(
    project_id: uuid.UUID,
    payload: MilestoneOrder,
    session: SessionDep,
    settings: SettingsDep,
    user: Assistant,
) -> list[MilestoneResponse]:
    today = today_in(settings.timezone)
    rows = await service.reorder(session, project_id, payload.milestone_ids)
    return [MilestoneResponse.of(service.view(item, today=today)) for item in rows]


@router.patch(
    "/milestones/{milestone_id}", response_model=MilestoneResponse, summary="Изменение вехи"
)
async def update_milestone(
    milestone_id: uuid.UUID,
    payload: MilestoneUpdate,
    session: SessionDep,
    settings: SettingsDep,
    user: Assistant,
) -> MilestoneResponse:
    milestone = await service.update(session, milestone_id, payload.to_patch())
    return MilestoneResponse.of(service.view(milestone, today=today_in(settings.timezone)))


@router.delete("/milestones/{milestone_id}", status_code=204, summary="Удаление вехи")
async def delete_milestone(milestone_id: uuid.UUID, session: SessionDep, user: Assistant) -> None:
    await service.delete(session, milestone_id)
