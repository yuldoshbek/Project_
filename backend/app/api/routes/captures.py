"""Захват — недавние записи и запись одной кнопкой.

Форма ответа — договор экрана `frontend/src/sections/capture/model.ts`: экран утверждён
заказчиком 28.09.2026 на вымышленных данных той же формы, и API написан под него
(CLAUDE.md, цикл блока). Разбор фразы — прежний `POST /api/v1/tasks/parse`.

Записывают оба: руководитель — свои просьбу и идею (ТЗ 6, допущение V17). Правило — в
`app.domain.capture.check_author`, а не послаблением `Assistant`: исключение видно в коде.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SettingsDep, is_demo
from app.api.security import CurrentUser
from app.api.transaction import transactional_router
from app.domain.capture import TEXT_MAX_LENGTH, CaptureKind
from app.domain.clock import now_utc
from app.domain.files import FileOwner
from app.domain.people import Role
from app.services import captures as service

router = transactional_router(tags=["захват"])


class CaptureOut(BaseModel):
    id: uuid.UUID
    kind: CaptureKind
    text: str
    due_on: date | None
    author: Role
    created_at: datetime
    destination: Literal["tasks", "inbox"]


class CapturesResponse(BaseModel):
    as_of: datetime
    recent: list[CaptureOut]
    is_demo: bool


class PhotoOwner(BaseModel):
    owner_type: FileOwner
    owner_id: uuid.UUID


class SavedCapture(CaptureOut):
    task_code: str | None
    """Номер заведённой задачи — для подтверждения «Задача заведена: TSK-…»."""
    photo_owner: PhotoOwner
    """К чему класть фото из того же касания: задача, идея или запись во входящих."""


def _out(view: service.CaptureView) -> dict[str, object]:
    return {
        "id": view.id,
        "kind": view.kind,
        "text": view.text,
        "due_on": view.due_on,
        "author": view.author,
        "created_at": view.created_at,
        "destination": view.destination,
    }


@router.get("/captures", response_model=CapturesResponse, summary="Захват: недавние записи")
async def read_captures(
    user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> CapturesResponse:
    view = await service.load(
        session, now=now_utc(), zone=ZoneInfo(settings.timezone), is_demo=is_demo(settings)
    )
    return CapturesResponse(
        as_of=view.as_of,
        recent=[CaptureOut.model_validate(_out(each)) for each in view.recent],
        is_demo=view.is_demo,
    )


class NewCaptureRequest(BaseModel):
    # Неизвестное поле — отказ, как и поле, которого у типа нет (`check_fields`): «due»
    # вместо «due_on» иначе дало бы запись без срока, которую человек считал бы со сроком.
    model_config = ConfigDict(extra="forbid")

    kind: CaptureKind
    text: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)
    due_on: date | None = None
    assignee_id: uuid.UUID | None = None
    type_code: str | None = Field(default=None, max_length=50)
    project_id: uuid.UUID | None = None


@router.post(
    "/captures",
    response_model=SavedCapture,
    status_code=status.HTTP_201_CREATED,
    summary="Запись одной кнопкой: задача и просьба — в «Задачи», остальное — во входящие",
)
async def create_capture(
    body: NewCaptureRequest, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> SavedCapture:
    saved = await service.save(
        session,
        user=user,
        data=service.NewCapture(
            kind=body.kind,
            text=body.text,
            due_on=body.due_on,
            assignee_id=body.assignee_id,
            type_code=body.type_code,
            project_id=body.project_id,
        ),
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
    )
    return SavedCapture.model_validate(
        {
            **_out(saved.view),
            "task_code": saved.view.task_code,
            "photo_owner": {"owner_type": saved.record_type, "owner_id": saved.record_id},
        }
    )
