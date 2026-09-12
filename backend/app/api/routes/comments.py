"""Комментарии и ход событий по записи.

Реплики и изменения отдаются **одним потоком** (`GET /timeline`), а не двумя списками:
смысл обсуждения в порядке — кто на что отвечал и что за чем последовало, — и два списка
рядом читатель сводит в голове, обычно неверно.

Читать может любой вошедший, писать — только помощник (ADR-0011). Править и удалять —
только автор реплики; сегодня это одно и то же, но решение руководителя по проекту
(ORB-062) ляжет в ту же ленту за его подписью.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep
from app.api.security import Assistant, get_active_user
from app.api.transaction import transactional_router
from app.domain.comments import BODY_MAX_LENGTH, CommentTarget
from app.services import comments as service
from app.services import timeline as timeline_service

router = transactional_router(tags=["обсуждение"], dependencies=[Depends(get_active_user)])


class PersonMention(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class CommentResponse(BaseModel):
    id: uuid.UUID
    entity_type: CommentTarget
    entity_id: uuid.UUID
    author_id: uuid.UUID | None
    created_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None

    # У удалённой реплики текста нет — не пустая строка, а его отсутствие: читатель должен
    # отличить «здесь было и убрали» от «здесь ничего не писали».
    body: str | None
    mentioned: list[PersonMention]

    @classmethod
    def of(cls, view: service.CommentView) -> CommentResponse:
        comment = view.comment
        return cls(
            id=comment.id,
            entity_type=CommentTarget(comment.entity_type),
            entity_id=comment.entity_id,
            author_id=comment.author_id,
            created_at=comment.created_at,
            edited_at=comment.edited_at,
            deleted_at=comment.deleted_at,
            body=view.body,
            mentioned=[PersonMention.model_validate(person) for person in view.mentioned],
        )


class CommentCreate(BaseModel):
    entity_type: CommentTarget
    entity_id: uuid.UUID
    body: Annotated[str, Field(min_length=1, max_length=BODY_MAX_LENGTH)]


class CommentUpdate(BaseModel):
    body: Annotated[str, Field(min_length=1, max_length=BODY_MAX_LENGTH)]


class TimelineEventResponse(BaseModel):
    """Событие ленты: либо реплика, либо изменение.

    Один тип на оба вида, а не два разных: лента показывается одним списком, и разбирать
    её на клиенте по наличию полей — та же работа, что и по полю `kind`, только без имени.
    """

    kind: timeline_service.EventKind
    at: datetime
    actor_id: uuid.UUID | None
    actor_name: str | None
    comment: CommentResponse | None = None
    action: str | None = None
    changes: dict[str, Any] | None = None
    subject: str | None = None

    @classmethod
    def of(cls, event: timeline_service.TimelineEvent) -> TimelineEventResponse:
        return cls(
            kind=event.kind,
            at=event.at,
            actor_id=event.actor_id,
            actor_name=event.actor_name,
            comment=None if event.comment is None else CommentResponse.of(event.comment),
            action=event.action,
            changes=event.changes,
            subject=event.subject,
        )


@router.get("/comments", response_model=list[CommentResponse], summary="Лента обсуждения")
async def list_comments(
    session: SessionDep,
    entity_type: Annotated[CommentTarget, Query(description="Проект или задача")],
    entity_id: Annotated[uuid.UUID, Query()],
) -> list[CommentResponse]:
    views = await service.list_for(session, entity_type, entity_id)
    return [CommentResponse.of(view) for view in views]


@router.post(
    "/comments", response_model=CommentResponse, status_code=201, summary="Новый комментарий"
)
async def create_comment(
    payload: CommentCreate, session: SessionDep, user: Assistant
) -> CommentResponse:
    view = await service.create(
        session,
        service.CommentDraft(
            entity_type=payload.entity_type, entity_id=payload.entity_id, body=payload.body
        ),
        author=user,
    )
    return CommentResponse.of(view)


@router.patch(
    "/comments/{comment_id}", response_model=CommentResponse, summary="Правка комментария"
)
async def update_comment(
    comment_id: uuid.UUID, payload: CommentUpdate, session: SessionDep, user: Assistant
) -> CommentResponse:
    view = await service.update(session, comment_id, payload.body, author=user)
    return CommentResponse.of(view)


@router.delete("/comments/{comment_id}", status_code=204, summary="Удаление комментария")
async def delete_comment(comment_id: uuid.UUID, session: SessionDep, user: Assistant) -> None:
    """Удаление мягкое: реплика остаётся в ленте следом, но без текста."""
    await service.delete(session, comment_id, author=user)


@router.get(
    "/timeline", response_model=list[TimelineEventResponse], summary="Ход событий по записи"
)
async def read_timeline(
    session: SessionDep,
    entity_type: Annotated[CommentTarget, Query(description="Проект или задача")],
    entity_id: Annotated[uuid.UUID, Query()],
) -> list[TimelineEventResponse]:
    events = await timeline_service.of(session, entity_type, entity_id)
    return [TimelineEventResponse.of(event) for event in events]
