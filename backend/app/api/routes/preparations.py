"""Доклады и мероприятия — подготовка, чек-лист, запросы сведений.

Форма ответа — договор экрана `frontend/src/sections/reports/model.ts`. Решения и вопросы по
подготовке — прежние `/decisions` и `/questions` с `target_type = preparation`.

Подготовку ведёт помощник (`Assistant`): создаёт, меняет этап, отмечает пункты и
полученные сведения. Руководитель смотрит (`CurrentUser`) и решает кнопками Пульта.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SettingsDep, is_demo
from app.api.security import Assistant, CurrentUser
from app.api.transaction import transactional_router
from app.domain.clock import local_date, now_utc
from app.domain.preparations import (
    TEXT_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    Addressee,
    PreparationKind,
    PrepStage,
    SourceKind,
)
from app.services import preparations as service

router = transactional_router(tags=["доклады"])

Step = Literal["awaiting_decision", "overdue", "burning", "blocked_by_others", "silent"]


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str


class SourceOut(BaseModel):
    kind: SourceKind
    id: uuid.UUID
    name: str


class DelayOut(BaseModel):
    source: SourceOut
    count: int
    days: int
    requests: list[uuid.UUID]


class LinkOut(BaseModel):
    type: Literal["project"]
    id: uuid.UUID
    title: str


class CountsOut(BaseModel):
    done: int
    total: int


class RequestCountsOut(BaseModel):
    total: int
    received: int
    overdue: int


class PreparationOut(BaseModel):
    id: uuid.UUID
    kind: PreparationKind
    title: str
    addressee: Addressee | None
    show_on: date
    start_on: date | None
    responsible: PersonOut | None
    stage: PrepStage
    link: LinkOut | None
    checklist: CountsOut
    requests: RequestCountsOut
    delays: list[DelayOut]
    days_left: int
    step: Step | None
    deviation: int
    version: int


class ItemOut(BaseModel):
    id: uuid.UUID
    text: str
    is_done: bool
    version: int


class InfoRequestOut(BaseModel):
    id: uuid.UUID
    what: str
    source: SourceOut
    due_on: date | None
    received_on: date | None
    state: Literal["requested", "received", "overdue"]
    late_days: int
    version: int


class PreparationCardOut(PreparationOut):
    items: list[ItemOut]
    info_requests: list[InfoRequestOut]


class NearestOut(BaseModel):
    id: uuid.UUID
    title: str
    days_left: int
    missing: int
    delay: DelayOut | None


class ReadinessAnswer(BaseModel):
    key: Literal["readiness"]
    nearest: NearestOut | None
    count: int
    rows: list[uuid.UUID]


class StartNowAnswer(BaseModel):
    key: Literal["start_now"]
    count: int
    rows: list[uuid.UUID]


QuestionAnswer = Annotated[ReadinessAnswer | StartNowAnswer, Field(discriminator="key")]


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None


class ProjectOut(BaseModel):
    id: uuid.UUID
    code: str
    title: str


class ReportsResponse(BaseModel):
    as_of: datetime
    questions: list[QuestionAnswer]
    items: list[PreparationOut]
    people: list[PersonOut]
    organizations: list[OrganizationOut]
    projects: list[ProjectOut]
    is_demo: bool


class Created(BaseModel):
    id: uuid.UUID


@router.get("/preparations", response_model=ReportsResponse, summary="Доклады и мероприятия")
async def read_preparations(
    user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> ReportsResponse:
    view = await service.load(
        session, now=now_utc(), zone=ZoneInfo(settings.timezone), is_demo=is_demo(settings)
    )
    return ReportsResponse.model_validate(view)


@router.get(
    "/preparations/{preparation_id}",
    response_model=PreparationCardOut,
    summary="Карточка подготовки",
)
async def read_preparation(
    preparation_id: uuid.UUID, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> PreparationCardOut:
    found = await service.card(
        session, preparation_id=preparation_id, now=now_utc(), zone=ZoneInfo(settings.timezone)
    )
    return PreparationCardOut.model_validate(found)


class NewPreparationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PreparationKind
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    show_on: date
    start_on: date | None = None
    addressee: Addressee | None = None
    responsible_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


@router.post(
    "/preparations",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Новая подготовка",
)
async def create_preparation(
    body: NewPreparationRequest, user: Assistant, session: SessionDep
) -> Created:
    prep_id = await service.create(
        session,
        data=service.NewPreparation(
            kind=body.kind,
            title=body.title,
            show_on=body.show_on,
            start_on=body.start_on,
            addressee=body.addressee,
            responsible_id=body.responsible_id,
            project_id=body.project_id,
        ),
    )
    return Created(id=prep_id)


class StageRequest(BaseModel):
    stage: PrepStage
    version: int


@router.put(
    "/preparations/{preparation_id}/stage",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Этап подготовки",
)
async def update_stage(
    preparation_id: uuid.UUID, body: StageRequest, user: Assistant, session: SessionDep
) -> None:
    await service.set_stage(
        session, preparation_id=preparation_id, stage=body.stage, version=body.version
    )


class ItemRequest(BaseModel):
    text: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)


@router.post(
    "/preparations/{preparation_id}/items",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Пункт чек-листа",
)
async def create_item(
    preparation_id: uuid.UUID, body: ItemRequest, user: Assistant, session: SessionDep
) -> Created:
    item_id = await service.add_item(session, preparation_id=preparation_id, text=body.text)
    return Created(id=item_id)


class ToggleRequest(BaseModel):
    done: bool
    version: int


@router.put(
    "/preparations/{preparation_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отметить пункт чек-листа",
)
async def toggle_item(
    preparation_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ToggleRequest,
    user: Assistant,
    session: SessionDep,
) -> None:
    await service.toggle_item(
        session,
        preparation_id=preparation_id,
        item_id=item_id,
        done=body.done,
        version=body.version,
    )


class NewInfoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    what: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)
    source_kind: SourceKind
    source_id: uuid.UUID
    due_on: date | None = None


@router.post(
    "/preparations/{preparation_id}/requests",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Запрос сведений",
)
async def create_request(
    preparation_id: uuid.UUID, body: NewInfoRequest, user: Assistant, session: SessionDep
) -> Created:
    request_id = await service.add_request(
        session,
        preparation_id=preparation_id,
        data=service.NewRequest(
            what=body.what,
            source_kind=body.source_kind,
            source_id=body.source_id,
            due_on=body.due_on,
        ),
    )
    return Created(id=request_id)


class ReceivedRequest(BaseModel):
    received_on: date | None
    version: int


@router.put(
    "/preparations/{preparation_id}/requests/{request_id}/received",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Сведения получены",
)
async def receive_request(
    preparation_id: uuid.UUID,
    request_id: uuid.UUID,
    body: ReceivedRequest,
    user: Assistant,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    await service.receive(
        session,
        preparation_id=preparation_id,
        request_id=request_id,
        received_on=body.received_on,
        version=body.version,
        today=local_date(now_utc(), ZoneInfo(settings.timezone)),
    )
