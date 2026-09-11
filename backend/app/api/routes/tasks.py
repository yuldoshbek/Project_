"""Задачи: чтение и изменение.

`is_overdue` и `days_overdue` приходят в ответе, но в базе их нет: просрочка —
вычисляемое состояние, а не статус ([ADR-0004](../../../docs/adr/ADR-0004-overdue-is-computed.md)).
Хранить её значило бы потерять исходное состояние работы: задача бывает «в работе» и
просроченной одновременно, а один столбец такого не выражает.

Читать может любой вошедший, изменять — только помощник (ADR-0011).
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SettingsDep
from app.api.security import Assistant, get_active_user
from app.api.transaction import transactional_router
from app.domain.checklists import ChecklistProgress
from app.domain.clock import now_utc, today_in
from app.domain.dictionaries import TaskStatus
from app.services import checklists as checklist_service
from app.services import tasks as service

router = transactional_router(tags=["задачи"], dependencies=[Depends(get_active_user)])

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

    # Прогресс чек-листа приходит вместе с задачей, а не отдельным запросом на строку:
    # он нужен в списке (критерий ORB-015), а список — это сотни строк. Не хранится:
    # считается из самих пунктов (`app.domain.checklists`).
    checklist_done: int
    checklist_total: int
    # Доля считается на сервере, а не на клиенте: правило «пустой чек-лист — это не ноль
    # процентов» должно жить в одном месте, иначе второй экран однажды нарисует нулевую
    # полосу там, где чек-листа нет вовсе, и она прочитается как тревога.
    checklist_percent: int | None

    @classmethod
    def of(
        cls, item: service.TaskView, progress: ChecklistProgress = checklist_service.EMPTY
    ) -> TaskResponse:
        computed = {
            "is_overdue",
            "days_overdue",
            "checklist_done",
            "checklist_total",
            "checklist_percent",
        }
        stored = {
            name: getattr(item.task, name) for name in cls.model_fields if name not in computed
        }
        return cls(
            **stored,
            is_overdue=item.is_overdue,
            days_overdue=item.days_overdue,
            checklist_done=progress.done,
            checklist_total=progress.total,
            checklist_percent=progress.percent,
        )


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
    curator_person_id: Annotated[uuid.UUID | None, Query(description="Куратор проекта")] = None,
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
            curator_person_id=curator_person_id,
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

    progress = await checklist_service.progress_for(session, [item.task.id for item in rows])
    return [
        TaskResponse.of(item, progress.get(item.task.id, checklist_service.EMPTY)) for item in rows
    ]


# Выгрузка объявлена **до** `/tasks/{task_id}`, и это не вкусовщина: FastAPI берёт
# первый подошедший маршрут, и `export.csv` иначе попадает в него как идентификатор.
# Ответ при этом не «не найдено», а 422 про неразобранный UUID — и полчаса уходит на
# поиск ошибки там, где её нет.
CSV_COLUMNS = (
    ("code", "Номер"),
    ("title", "Название"),
    ("status", "Статус"),
    ("priority", "Приоритет"),
    ("due_at", "Срок"),
    ("is_overdue", "Просрочена"),
    ("checklist", "Чек-лист"),
    ("assignee", "Исполнитель"),
    ("project", "Проект"),
)


@router.get("/tasks/export.csv", summary="Выгрузка выборки")
async def export_tasks(
    session: SessionDep,
    settings: SettingsDep,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    direction_id: Annotated[uuid.UUID | None, Query()] = None,
    curator_person_id: Annotated[uuid.UUID | None, Query()] = None,
    assignee_person_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[TaskStatus | None, Query()] = None,
    priority_code: Annotated[str | None, Query()] = None,
    is_control: Annotated[bool | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
    without_project: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    due_before: Annotated[datetime | None, Query()] = None,
    sort_by: Annotated[str, Query()] = "due_at",
    descending: Annotated[bool, Query()] = False,
) -> Response:
    """Та же выборка, что на экране, файлом.

    Собирается на сервере, а не из того, что уже лежит на странице: выгрузка — точка
    выхода наружу, и задачи закрытых проектов через неё не проходят (ADR-0007).
    Собери файл в браузере — и проверка осталась бы на клиенте, то есть нигде.

    Разделитель — точка с запятой, кодировка с меткой порядка байтов: Excel с русской
    локалью иначе раскладывает CSV в одну колонку и портит кириллицу, и первое, что
    делает человек, — закрывает файл.
    """
    rows = await service.list_for_export(
        session,
        service.TaskFilter(
            project_id=project_id,
            direction_id=direction_id,
            curator_person_id=curator_person_id,
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

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow([title for _, title in CSV_COLUMNS])
    for item in rows:
        writer.writerow([_cell(item, field, settings.timezone) for field, _ in CSV_COLUMNS])

    return Response(
        content=buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        # Дата в имени: иначе в папке загрузок копятся «orbita-tasks (3).csv», и через
        # неделю невозможно понять, какая выгрузка от какого числа.
        headers={
            "Content-Disposition": (
                f'attachment; filename="orbita-tasks-{today_in(settings.timezone)}.csv"'
            )
        },
    )


def _cell(row: service.ExportRow, field: str, timezone: str) -> str:
    value = getattr(row, field)
    if field == "is_overdue":
        return "да" if value else ""
    if value is None:
        return ""
    if isinstance(value, datetime):
        # Ташкентское время, а не UTC: хранение и показ — разные вещи (инвариант 5), а
        # файл читает человек. Вид «14.09.2026 17:00» Excel с русской локалью распознаёт
        # как дату, а не как строку, — иначе по сроку нельзя ни отсортировать, ни считать.
        return value.astimezone(ZoneInfo(timezone)).strftime("%d.%m.%Y %H:%M")
    return str(value)


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
    return TaskResponse.of(
        service.view(task, now=now_utc()),
        await checklist_service.progress_of(session, task.id),
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse, summary="Карточка задачи")
async def read_task(task_id: uuid.UUID, session: SessionDep) -> TaskResponse:
    task = await service.get(session, task_id)
    return TaskResponse.of(
        service.view(task, now=now_utc()),
        await checklist_service.progress_of(session, task.id),
    )


@router.patch("/tasks/{task_id}", response_model=TaskResponse, summary="Изменение задачи")
async def update_task(
    task_id: uuid.UUID, payload: TaskUpdate, session: SessionDep, user: Assistant
) -> TaskResponse:
    task = await service.update(session, task_id, payload.to_patch())
    return TaskResponse.of(
        service.view(task, now=now_utc()),
        await checklist_service.progress_of(session, task.id),
    )


@router.delete("/tasks/{task_id}", status_code=204, summary="Удаление задачи")
async def delete_task(task_id: uuid.UUID, session: SessionDep, user: Assistant) -> None:
    await service.delete(session, task_id)
