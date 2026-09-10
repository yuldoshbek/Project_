"""Задачи: чтение и изменение.

`is_overdue` и `days_overdue` приходят в ответе, но в базе их нет: просрочка —
вычисляемое состояние, а не статус ([ADR-0004](../../../docs/adr/ADR-0004-overdue-is-computed.md)).
Хранить её значило бы потерять исходное состояние работы: задача бывает «в работе» и
просроченной одновременно, а один столбец такого не выражает.

Читать может любой вошедший, изменять — только помощник (ADR-0011).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SettingsDep
from app.api.security import Assistant, get_active_user
from app.domain.clock import today_in
from app.domain.dictionaries import TaskStatus
from app.domain.tasks import now_utc
from app.services import tasks as service

router = APIRouter(tags=["задачи"], dependencies=[Depends(get_active_user)])

TITLE_MAX = 300


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    project_id: uuid.UUID | None
    title: str
    description: str | None
    assignee_person_id: uuid.UUID | None
    author_id: uuid.UUID | None
    status: TaskStatus
    priority_code: str
    due_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    is_control: bool
    is_overdue: bool
    days_overdue: int

    @classmethod
    def of(cls, item: service.TaskView) -> TaskResponse:
        stored = {
            name: getattr(item.task, name)
            for name in cls.model_fields
            if name not in {"is_overdue", "days_overdue"}
        }
        return cls(**stored, is_overdue=item.is_overdue, days_overdue=item.days_overdue)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    priority_code: str
    status: TaskStatus = TaskStatus.NEW
    project_id: uuid.UUID | None = None
    description: str | None = None
    assignee_person_id: uuid.UUID | None = None
    due_at: datetime | None = None
    is_control: bool = False


class TaskUpdate(BaseModel):
    """Частичное изменение: непереданное поле остаётся как было."""

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    description: str | None = None
    project_id: uuid.UUID | None = None
    assignee_person_id: uuid.UUID | None = None
    status: TaskStatus | None = None
    priority_code: str | None = None
    due_at: datetime | None = None
    is_control: bool | None = None

    def to_patch(self) -> service.TaskPatch:
        return service.TaskPatch(**{name: getattr(self, name) for name in self.model_fields_set})


@router.get("/tasks", response_model=list[TaskResponse], summary="База задач")
async def list_tasks(
    session: SessionDep,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    direction_id: Annotated[uuid.UUID | None, Query(description="Через проект")] = None,
    assignee_person_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[TaskStatus | None, Query()] = None,
    priority_code: Annotated[str | None, Query()] = None,
    is_control: Annotated[bool | None, Query(description="Поручения на контроле")] = None,
    overdue: Annotated[bool | None, Query(description="Просроченные (ADR-0004)")] = None,
    without_project: Annotated[bool | None, Query(description="Только задачи вне проекта")] = None,
    search: Annotated[str | None, Query(description="Совпадение по части названия")] = None,
    due_before: Annotated[datetime | None, Query(description="Срок раньше указанного")] = None,
    sort_by: Annotated[
        str, Query(description=f"Одно из: {', '.join(service.SORTABLE)}")
    ] = "due_at",
    descending: Annotated[bool, Query()] = False,
) -> list[TaskResponse]:
    rows = await service.list_tasks(
        session,
        service.TaskFilter(
            project_id=project_id,
            direction_id=direction_id,
            assignee_person_id=assignee_person_id,
            status=status,
            priority_code=priority_code,
            is_control=is_control,
            overdue=overdue,
            without_project=without_project,
            search=search,
            due_before=due_before,
        ),
        sort_by=sort_by,
        descending=descending,
    )
    return [TaskResponse.of(item) for item in rows]


@router.post("/tasks", response_model=TaskResponse, status_code=201, summary="Новая задача")
async def create_task(
    payload: TaskCreate, session: SessionDep, settings: SettingsDep, user: Assistant
) -> TaskResponse:
    task = await service.create(
        session,
        service.TaskDraft(**payload.model_dump()),
        author_id=user.id,
        today=today_in(settings.timezone),
    )
    return TaskResponse.of(service.view(task, now=now_utc()))


@router.get("/tasks/{task_id}", response_model=TaskResponse, summary="Карточка задачи")
async def read_task(task_id: uuid.UUID, session: SessionDep) -> TaskResponse:
    task = await service.get(session, task_id)
    return TaskResponse.of(service.view(task, now=now_utc()))


@router.patch("/tasks/{task_id}", response_model=TaskResponse, summary="Изменение задачи")
async def update_task(
    task_id: uuid.UUID, payload: TaskUpdate, session: SessionDep, user: Assistant
) -> TaskResponse:
    task = await service.update(session, task_id, payload.to_patch())
    return TaskResponse.of(service.view(task, now=now_utc()))


@router.delete("/tasks/{task_id}", status_code=204, summary="Удаление задачи")
async def delete_task(task_id: uuid.UUID, session: SessionDep, user: Assistant) -> None:
    await service.delete(session, task_id)
