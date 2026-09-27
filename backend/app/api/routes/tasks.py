"""Задачи — раздел, карточка, разбор строки, новая задача, правка, статус, чек-лист.

Форма ответа — договор экрана `frontend/src/sections/tasks/model.ts`: экран утверждён
заказчиком 27.09.2026 на вымышленных данных той же формы, и API написан под него
(CLAUDE.md, цикл блока). Эндпоинта, которому нет места на экране, здесь нет.

Смотрят оба, вносит помощник (`Assistant`). Разбор строки ничего не записывает и доступен
обоим — как «что если» у проектов.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import Query, status
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, SettingsDep, is_demo
from app.api.security import Assistant, CurrentUser
from app.api.transaction import transactional_router
from app.domain.checklists import ITEM_MAX_LENGTH
from app.domain.clock import now_utc
from app.domain.dictionaries import TaskStatus
from app.domain.projects import DESCRIPTION_MAX_LENGTH
from app.domain.tasks import TITLE_MAX_LENGTH
from app.services import tasks as service

router = transactional_router(tags=["задачи"])

PARSE_MAX_LENGTH = 1000
"""Строка захвата — одна фраза. Тысяча знаков — с большим запасом."""


class Ref(BaseModel):
    id: uuid.UUID
    name: str


class TaskType(BaseModel):
    code: str
    name: str


class ProjectRef(BaseModel):
    id: uuid.UUID
    code: str
    title: str


class IjroRef(BaseModel):
    id: uuid.UUID
    label: str


class Progress(BaseModel):
    done: int
    total: int


class TaskCard(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    type: TaskType | None
    status: TaskStatus
    assignee: Ref | None
    due_on: date | None
    original_due_on: date | None
    moves: int
    horizon: str
    step: str | None
    deviation: int
    project: ProjectRef | None
    ijro: IjroRef | None
    checklist: Progress
    completed_on: date | None
    version: int


class LoadRow(BaseModel):
    person: Ref
    overdue: int
    burning: int
    open: int


class TasksResponse(BaseModel):
    as_of: datetime
    items: list[TaskCard]
    types: list[TaskType]
    people: list[Ref]
    projects: list[ProjectRef]
    load: list[LoadRow]
    is_demo: bool


class ChecklistItem(BaseModel):
    id: uuid.UUID
    text: str
    is_done: bool
    version: int


class Question(BaseModel):
    text: str
    asked_on: date


class TaskDetail(TaskCard):
    description: str | None
    checklist_items: list[ChecklistItem]
    created_on: date
    question: Question | None
    transitions: list[TaskStatus]


def _card_fields(card: service.CardView) -> dict[str, object]:
    return {
        "id": card.id,
        "code": card.code,
        "title": card.title,
        "type": TaskType(code=card.type[0], name=card.type[1]) if card.type else None,
        "status": TaskStatus(card.status),
        "assignee": Ref(id=card.assignee.id, name=card.assignee.name) if card.assignee else None,
        "due_on": card.due_on,
        "original_due_on": card.original_due_on,
        "moves": card.moves,
        "horizon": card.horizon.value,
        "step": card.step.value if card.step else None,
        "deviation": card.deviation,
        "project": ProjectRef(id=card.project[0], code=card.project[1], title=card.project[2])
        if card.project
        else None,
        "ijro": IjroRef(id=card.ijro[0], label=card.ijro[1]) if card.ijro else None,
        "checklist": Progress(done=card.checklist_done, total=card.checklist_total),
        "completed_on": card.completed_on,
        "version": card.version,
    }


def _detail(view: service.DetailView) -> TaskDetail:
    return TaskDetail(
        **_card_fields(view.card),
        description=view.description,
        checklist_items=[
            ChecklistItem(id=item.id, text=item.text, is_done=item.is_done, version=item.version)
            for item in view.items
        ],
        created_on=view.created_on,
        question=Question(text=view.question[0], asked_on=view.question[1])
        if view.question
        else None,
        transitions=view.transitions,
    )


@router.get("/tasks", response_model=TasksResponse, summary="Задачи: весь раздел")
async def read_tasks(
    user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> TasksResponse:
    view = await service.load(
        session,
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
        locale=user.locale,
        is_demo=is_demo(settings),
    )
    return TasksResponse(
        as_of=view.as_of,
        items=[TaskCard(**_card_fields(card)) for card in view.items],
        types=[TaskType(code=code, name=name) for code, name in view.types],
        people=[Ref(id=person.id, name=person.name) for person in view.people],
        projects=[ProjectRef(id=ref, code=code, title=title) for ref, code, title in view.projects],
        load=[
            LoadRow(
                person=Ref(id=row.person.id, name=row.person.name),
                overdue=row.overdue,
                burning=row.burning,
                open=row.open,
            )
            for row in view.load
        ],
        is_demo=view.is_demo,
    )


@router.get("/tasks/{task_id}", response_model=TaskDetail, summary="Карточка задачи")
async def read_task(
    task_id: uuid.UUID, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> TaskDetail:
    return _detail(
        await service.detail(
            session,
            task_id=task_id,
            now=now_utc(),
            zone=ZoneInfo(settings.timezone),
            locale=user.locale,
        )
    )


class ParseRequest(BaseModel):
    text: str = Field(max_length=PARSE_MAX_LENGTH)


class Matched(BaseModel):
    type: str | None
    due: str | None
    assignee: str | None


class ParsedLine(BaseModel):
    title: str
    type_code: str | None
    due_on: date | None
    assignee_id: uuid.UUID | None
    matched: Matched


@router.post(
    "/tasks/parse",
    response_model=ParsedLine,
    summary="Разбор строки: тип, срок и ответственный — без записи",
)
async def parse_line(
    body: ParseRequest, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> ParsedLine:
    parsed = await service.parse(
        session, text=body.text, now=now_utc(), zone=ZoneInfo(settings.timezone)
    )
    assignee = parsed.assignee_id
    return ParsedLine(
        title=parsed.title,
        type_code=parsed.type_code,
        due_on=parsed.due_on,
        assignee_id=assignee if isinstance(assignee, uuid.UUID) else None,
        matched=Matched(
            type=parsed.matched_type, due=parsed.matched_due, assignee=parsed.matched_assignee
        ),
    )


class NewTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    type_code: str | None = Field(default=None, max_length=50)
    due_on: date | None = None
    assignee_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


@router.post(
    "/tasks",
    response_model=TaskDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Новая задача: обязательно одно название",
)
async def create_task(
    body: NewTaskRequest, user: Assistant, session: SessionDep, settings: SettingsDep
) -> TaskDetail:
    zone = ZoneInfo(settings.timezone)
    now = now_utc()
    task_id = await service.create(
        session,
        user=user,
        data=service.NewTask(
            title=body.title,
            type_code=body.type_code,
            due_on=body.due_on,
            assignee_id=body.assignee_id,
            project_id=body.project_id,
        ),
        now=now,
        zone=zone,
    )
    return _detail(
        await service.detail(session, task_id=task_id, now=now, zone=zone, locale=user.locale)
    )


class TaskEditRequest(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    type_code: str | None = Field(default=None, max_length=50)
    due_on: date | None = None
    assignee_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    version: int


@router.put(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Сведения задачи: название, тип, ответственный, срок, проект, описание",
)
async def update_task(
    task_id: uuid.UUID,
    body: TaskEditRequest,
    user: Assistant,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    await service.edit(
        session,
        task_id=task_id,
        data=service.TaskEdit(
            title=body.title,
            type_code=body.type_code,
            due_on=body.due_on,
            assignee_id=body.assignee_id,
            project_id=body.project_id,
            description=body.description,
            version=body.version,
        ),
        zone=ZoneInfo(settings.timezone),
    )


class StatusRequest(BaseModel):
    status: TaskStatus
    version: int


@router.put(
    "/tasks/{task_id}/status",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Статус задачи — по графу переходов",
)
async def update_status(
    task_id: uuid.UUID, body: StatusRequest, user: Assistant, session: SessionDep
) -> None:
    await service.set_status(
        session, task_id=task_id, status=body.status, version=body.version, now=now_utc()
    )


class NewItemRequest(BaseModel):
    text: str = Field(min_length=1, max_length=ITEM_MAX_LENGTH)


class Created(BaseModel):
    id: uuid.UUID


@router.post(
    "/tasks/{task_id}/checklist",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Новый пункт чек-листа",
)
async def create_item(
    task_id: uuid.UUID, body: NewItemRequest, user: Assistant, session: SessionDep
) -> Created:
    return Created(id=await service.add_item(session, task_id=task_id, text=body.text))


class ItemRequest(BaseModel):
    is_done: bool
    version: int


@router.put(
    "/tasks/{task_id}/checklist/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отметить пункт чек-листа",
)
async def update_item(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ItemRequest,
    user: Assistant,
    session: SessionDep,
) -> None:
    await service.toggle_item(
        session, task_id=task_id, item_id=item_id, done=body.is_done, version=body.version
    )


@router.delete(
    "/tasks/{task_id}/checklist/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Убрать пункт чек-листа",
)
async def delete_item(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    user: Assistant,
    session: SessionDep,
    version: int = Query(description="Версия пункта, которую видел человек"),
) -> None:
    await service.remove_item(session, task_id=task_id, item_id=item_id, version=version)
