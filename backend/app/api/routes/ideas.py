"""Идеи и карты — путь идеи до проекта, интеллект-карты.

Форма ответа — договор экрана `frontend/src/sections/ideas/model.ts`.

Идею записывают и правят оба (ТЗ 6: руководитель «записать идею»); решает руководитель
(`Leader`) — это его «да». Карта общая: узлы правят оба, превращение узла в проект или
задачу — тоже оба, роль подписывает действие (инвариант 13).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SettingsDep, is_demo
from app.api.security import CurrentUser, Leader
from app.api.transaction import transactional_router
from app.domain.attention import Attention
from app.domain.clock import now_utc
from app.domain.ideas import (
    CANVAS_LIMIT,
    MAP_TITLE_MAX_LENGTH,
    NODE_TEXT_MAX_LENGTH,
    TEXT_MAX_LENGTH,
    IdeaStep,
    MapMode,
    Outcome,
)
from app.repos.ideas import Link, MapRow
from app.services import ideas as service

router = transactional_router(tags=["идеи"])


class Created(BaseModel):
    id: uuid.UUID


class LinkOut(BaseModel):
    type: Literal["project", "task"]
    id: uuid.UUID
    code: str
    title: str


def _link(link: Link | None) -> LinkOut | None:
    if link is None:
        return None
    kind: Literal["project", "task"] = "project" if link.type == "project" else "task"
    return LinkOut(type=kind, id=link.id, code=link.code, title=link.title)


class PhotoOut(BaseModel):
    id: uuid.UUID
    name: str


class IdeaOut(BaseModel):
    id: uuid.UUID
    text: str
    author: Literal["assistant", "leader"]
    step: IdeaStep
    outcome: Outcome | None
    created_at: datetime
    review_at: datetime | None
    decided_at: datetime | None
    waiting_days: int
    link: LinkOut | None
    photos: list[PhotoOut]
    version: int


class AwaitingAnswer(BaseModel):
    key: Literal["awaiting"]
    count: int
    oldest_days: int
    oldest_id: uuid.UUID | None
    rows: list[uuid.UUID]


class MapOut(BaseModel):
    id: uuid.UUID
    title: str
    mode: MapMode
    nodes: int
    linked: int
    changed_at: datetime
    version: int


class TypeOut(BaseModel):
    code: str
    name: str


class IdeasResponse(BaseModel):
    as_of: datetime
    questions: list[AwaitingAnswer]
    items: list[IdeaOut]
    maps: list[MapOut]
    project_types: list[TypeOut]
    is_demo: bool


def _map_out(row: MapRow) -> MapOut:
    return MapOut(
        id=row.id,
        title=row.title,
        mode=MapMode(row.mode),
        nodes=row.nodes,
        linked=row.linked,
        changed_at=row.changed_at,
        version=row.version,
    )


@router.get("/ideas", response_model=IdeasResponse, summary="Идеи и карты")
async def read_ideas(
    user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> IdeasResponse:
    view = await service.load(
        session,
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
        locale=user.locale,
        is_demo=is_demo(settings),
    )
    return IdeasResponse(
        as_of=view.as_of,
        questions=[
            AwaitingAnswer(
                key="awaiting",
                count=answer.count,
                oldest_days=answer.oldest_days,
                oldest_id=answer.oldest_id,
                rows=answer.rows,
            )
            for answer in view.questions
        ],
        items=[
            IdeaOut(
                id=item.row.id,
                text=item.row.text,
                author="leader" if item.row.author == "leader" else "assistant",
                step=IdeaStep(item.row.step),
                outcome=Outcome(item.row.outcome) if item.row.outcome else None,
                created_at=item.row.created_at,
                review_at=item.row.review_at,
                decided_at=item.row.decided_at,
                waiting_days=item.waiting_days,
                link=_link(item.row.link),
                photos=[PhotoOut(id=photo.id, name=photo.name) for photo in item.photos],
                version=item.row.version,
            )
            for item in view.items
        ],
        maps=[_map_out(row) for row in view.maps],
        project_types=[TypeOut(code=each.code, name=each.name) for each in view.project_types],
        is_demo=view.is_demo,
    )


class IdeaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)


@router.post(
    "/ideas", response_model=Created, status_code=status.HTTP_201_CREATED, summary="Новая идея"
)
async def create_idea(body: IdeaRequest, user: CurrentUser, session: SessionDep) -> Created:
    return Created(id=await service.create_idea(session, user=user, text=body.text))


class IdeaEditRequest(IdeaRequest):
    version: int


@router.put("/ideas/{idea_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Текст идеи")
async def edit_idea(
    idea_id: uuid.UUID, body: IdeaEditRequest, user: CurrentUser, session: SessionDep
) -> None:
    await service.edit_idea(session, idea_id=idea_id, text=body.text, version=body.version)


class VersionRequest(BaseModel):
    version: int


@router.put(
    "/ideas/{idea_id}/review", status_code=status.HTTP_204_NO_CONTENT, summary="На рассмотрение"
)
async def send_to_review(
    idea_id: uuid.UUID, body: VersionRequest, user: CurrentUser, session: SessionDep
) -> None:
    await service.to_review(session, idea_id=idea_id, version=body.version, now=now_utc())


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Outcome
    type_code: str | None = Field(default=None, max_length=60)
    version: int


class DecisionOut(BaseModel):
    created_id: uuid.UUID | None


@router.post(
    "/ideas/{idea_id}/decision", response_model=DecisionOut, summary="Решение руководителя"
)
async def decide(
    idea_id: uuid.UUID,
    body: DecisionRequest,
    user: Leader,
    session: SessionDep,
    settings: SettingsDep,
) -> DecisionOut:
    created = await service.decide(
        session,
        user=user,
        idea_id=idea_id,
        outcome=body.outcome,
        type_code=body.type_code,
        version=body.version,
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
    )
    return DecisionOut(created_id=created)


# --------------------------------------------------------------------------------------
# Карты
# --------------------------------------------------------------------------------------


class NodeOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    text: str
    x: int
    y: int
    link: LinkOut | None
    step: Attention | None
    deviation: int
    version: int


class MapResponse(MapOut):
    node_list: list[NodeOut]
    project_types: list[TypeOut]


@router.get("/maps/{map_id}", response_model=MapResponse, summary="Карта с узлами")
async def read_map(
    map_id: uuid.UUID, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> MapResponse:
    view = await service.card(
        session, map_id=map_id, now=now_utc(), zone=ZoneInfo(settings.timezone), locale=user.locale
    )
    return MapResponse(
        **_map_out(view.map).model_dump(),
        node_list=[
            NodeOut(
                id=node.row.id,
                parent_id=node.row.parent_id,
                text=node.row.text,
                x=node.row.x,
                y=node.row.y,
                link=_link(node.row.link),
                step=node.step,
                deviation=node.deviation,
                version=node.row.version,
            )
            for node in view.nodes
        ],
        project_types=[TypeOut(code=each.code, name=each.name) for each in view.project_types],
    )


class MapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAP_TITLE_MAX_LENGTH)
    mode: MapMode = MapMode.SKETCH


@router.post(
    "/maps", response_model=Created, status_code=status.HTTP_201_CREATED, summary="Новая карта"
)
async def create_map(body: MapRequest, user: CurrentUser, session: SessionDep) -> Created:
    return Created(id=await service.create_map(session, title=body.title, mode=body.mode))


class MapEditRequest(MapRequest):
    version: int


@router.put("/maps/{map_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Название и режим")
async def edit_map(
    map_id: uuid.UUID, body: MapEditRequest, user: CurrentUser, session: SessionDep
) -> None:
    await service.edit_map(
        session, map_id=map_id, title=body.title, mode=body.mode, version=body.version
    )


Coordinate = Field(ge=-CANVAS_LIMIT, le=CANVAS_LIMIT)


class NodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=NODE_TEXT_MAX_LENGTH)
    parent_id: uuid.UUID | None = None
    x: int = Coordinate
    y: int = Coordinate


@router.post(
    "/maps/{map_id}/nodes",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Новый узел",
)
async def add_node(
    map_id: uuid.UUID, body: NodeRequest, user: CurrentUser, session: SessionDep
) -> Created:
    node_id = await service.add_node(
        session, map_id=map_id, text=body.text, parent_id=body.parent_id, x=body.x, y=body.y
    )
    return Created(id=node_id)


class NodeTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=NODE_TEXT_MAX_LENGTH)
    version: int


@router.put(
    "/maps/{map_id}/nodes/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Подпись узла",
)
async def edit_node(
    map_id: uuid.UUID,
    node_id: uuid.UUID,
    body: NodeTextRequest,
    user: CurrentUser,
    session: SessionDep,
) -> None:
    await service.edit_node(
        session, map_id=map_id, node_id=node_id, text=body.text, version=body.version
    )


class PositionRequest(BaseModel):
    x: int = Coordinate
    y: int = Coordinate
    version: int


@router.put(
    "/maps/{map_id}/nodes/{node_id}/position",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Место узла на полотне",
)
async def move_node(
    map_id: uuid.UUID,
    node_id: uuid.UUID,
    body: PositionRequest,
    user: CurrentUser,
    session: SessionDep,
) -> None:
    await service.move_node(
        session, map_id=map_id, node_id=node_id, x=body.x, y=body.y, version=body.version
    )


class ParentRequest(BaseModel):
    parent_id: uuid.UUID | None
    version: int


@router.put(
    "/maps/{map_id}/nodes/{node_id}/parent",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Родитель узла",
)
async def set_parent(
    map_id: uuid.UUID,
    node_id: uuid.UUID,
    body: ParentRequest,
    user: CurrentUser,
    session: SessionDep,
) -> None:
    await service.set_parent(
        session, map_id=map_id, node_id=node_id, parent_id=body.parent_id, version=body.version
    )


class DeletedOut(BaseModel):
    deleted: int


@router.delete(
    "/maps/{map_id}/nodes/{node_id}", response_model=DeletedOut, summary="Убрать узел с ветвью"
)
async def delete_node(
    map_id: uuid.UUID,
    node_id: uuid.UUID,
    version: int,
    branch: Annotated[
        str,
        Query(
            pattern="^[0-9a-f]{8}$",
            description="Отпечаток ветви, которую видел человек: узлы и их версии",
        ),
    ],
    user: CurrentUser,
    session: SessionDep,
) -> DeletedOut:
    count = await service.delete_node(
        session, map_id=map_id, node_id=node_id, version=version, branch=branch
    )
    return DeletedOut(deleted=count)


class ConvertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["project", "task"]
    type_code: str | None = Field(default=None, max_length=60)
    version: int


@router.post(
    "/maps/{map_id}/nodes/{node_id}/convert",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Узел — в проект или задачу",
)
async def convert_node(
    map_id: uuid.UUID,
    node_id: uuid.UUID,
    body: ConvertRequest,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> Created:
    created = await service.convert_node(
        session,
        user=user,
        map_id=map_id,
        node_id=node_id,
        kind=Outcome(body.kind),
        type_code=body.type_code,
        version=body.version,
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
    )
    return Created(id=created)
