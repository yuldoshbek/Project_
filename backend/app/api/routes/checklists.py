"""Чек-листы и теги задач: чтение и изменение.

Прогресс чек-листа отдаётся не здесь, а вместе с задачей (`routes.tasks`): он нужен в
списке задач, и отдельным запросом на строку его не собрать. Здесь — сами пункты и теги.

Читать может любой вошедший, изменять — только помощник (ADR-0011).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep
from app.api.security import Assistant, get_active_user
from app.api.transaction import transactional_router
from app.domain.checklists import TAG_MAX_LENGTH
from app.services import checklists as service
from app.services import tags as tags_service

router = transactional_router(tags=["чек-листы и теги"], dependencies=[Depends(get_active_user)])

TEXT_MAX = 500


class ChecklistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    text: str
    is_done: bool
    sort_order: int


class ChecklistItemCreate(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=TEXT_MAX)]


class ChecklistItemPatch(BaseModel):
    text: Annotated[str | None, Field(default=None, min_length=1, max_length=TEXT_MAX)]
    is_done: bool | None = None


class ChecklistOrder(BaseModel):
    """Порядок целиком, а не сдвиг по одной позиции: см. `services.checklists.reorder`."""

    item_ids: list[uuid.UUID]


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class TaskTags(BaseModel):
    """Набор тегов задачи целиком.

    Набором, а не по одному: «добавь этот, убери тот» двумя запросами оставляет задачу в
    состоянии, которого пользователь не выбирал, если второй не дошёл.
    """

    names: list[Annotated[str, Field(min_length=1, max_length=TAG_MAX_LENGTH)]]


@router.get(
    "/tasks/{task_id}/checklist",
    response_model=list[ChecklistItemResponse],
    summary="Чек-лист задачи",
)
async def list_checklist(task_id: uuid.UUID, session: SessionDep) -> list[ChecklistItemResponse]:
    items = await service.list_for_task(session, task_id)
    return [ChecklistItemResponse.model_validate(item) for item in items]


@router.post(
    "/tasks/{task_id}/checklist",
    response_model=ChecklistItemResponse,
    status_code=201,
    summary="Новый пункт чек-листа",
)
async def create_checklist_item(
    task_id: uuid.UUID, payload: ChecklistItemCreate, session: SessionDep, user: Assistant
) -> ChecklistItemResponse:
    item = await service.create(session, task_id, service.ChecklistItemDraft(text=payload.text))
    return ChecklistItemResponse.model_validate(item)


@router.put(
    "/tasks/{task_id}/checklist/order",
    response_model=list[ChecklistItemResponse],
    summary="Порядок пунктов",
)
async def reorder_checklist(
    task_id: uuid.UUID, payload: ChecklistOrder, session: SessionDep, user: Assistant
) -> list[ChecklistItemResponse]:
    items = await service.reorder(session, task_id, payload.item_ids)
    return [ChecklistItemResponse.model_validate(item) for item in items]


@router.patch(
    "/checklist-items/{item_id}",
    response_model=ChecklistItemResponse,
    summary="Изменение пункта",
)
async def update_checklist_item(
    item_id: uuid.UUID, payload: ChecklistItemPatch, session: SessionDep, user: Assistant
) -> ChecklistItemResponse:
    patch = service.ChecklistItemPatch(**payload.model_dump(exclude_unset=True, exclude_none=True))
    item = await service.update(session, item_id, patch)
    return ChecklistItemResponse.model_validate(item)


@router.delete("/checklist-items/{item_id}", status_code=204, summary="Удаление пункта")
async def delete_checklist_item(item_id: uuid.UUID, session: SessionDep, user: Assistant) -> None:
    await service.delete(session, item_id)


@router.get("/tags", response_model=list[TagResponse], summary="Словарь тегов")
async def list_tags(session: SessionDep) -> list[TagResponse]:
    return [TagResponse.model_validate(tag) for tag in await tags_service.list_all(session)]


@router.get("/tasks/{task_id}/tags", response_model=list[TagResponse], summary="Теги задачи")
async def list_task_tags(task_id: uuid.UUID, session: SessionDep) -> list[TagResponse]:
    tags = await tags_service.list_for_task(session, task_id)
    return [TagResponse.model_validate(tag) for tag in tags]


@router.put("/tasks/{task_id}/tags", response_model=list[TagResponse], summary="Теги задачи")
async def set_task_tags(
    task_id: uuid.UUID, payload: TaskTags, session: SessionDep, user: Assistant
) -> list[TagResponse]:
    tags = await tags_service.set_for_task(session, task_id, payload.names)
    return [TagResponse.model_validate(tag) for tag in tags]
