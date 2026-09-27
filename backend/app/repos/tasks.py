"""Read-модель раздела «Задачи»: строка списка, карточка, справочники формы.

Число запросов не зависит от числа задач — по одному на признак: сами задачи со связями,
счёт чек-листов, переносы из журнала. Задача на запрос превратила бы список из пяти тысяч
задач (ТЗ 9) в пять тысяч обращений к базе (CLAUDE.md, «Read-модель на экран»).

Здесь только чтение и то, что нужно для записи: объекты, которые сервис правит. Ступени,
группа по сроку и «кто перегружен» считает `app.services.metrics`.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit import AuditAction
from app.domain.dictionaries import ProjectStatus
from app.domain.pult import TASKS, AuditEntry
from app.repos.models import (
    AuditLog,
    IjroAssignment,
    Person,
    Project,
    Task,
    TaskChecklistItem,
    TaskTypeRef,
)
from app.repos.projects import Names

PROJECT_TERMINAL = [status.value for status in ProjectStatus if status.is_terminal]


@dataclass(slots=True)
class TaskRow:
    """Задача со всем, что показывает строка списка, — без вычисленных чисел."""

    id: uuid.UUID
    code: str
    title: str
    type_code: str | None
    type_names: Names | None
    status: str
    assignee_id: uuid.UUID | None
    assignee_name: str | None
    due_at: datetime | None
    original_due_at: datetime | None
    project_id: uuid.UUID | None
    project_code: str | None
    project_title: str | None
    project_status: str | None
    ijro_id: uuid.UUID | None
    ijro_code: str | None
    completed_at: datetime | None
    created_at: datetime
    description: str | None
    version: int
    checklist_done: int = 0
    checklist_total: int = 0
    due_changes: list[AuditEntry] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ItemRow:
    id: uuid.UUID
    text: str
    is_done: bool
    version: int


def _scoped(statement: Select[Any], column: Any, ids: Collection[uuid.UUID] | None) -> Select[Any]:
    return statement if ids is None else statement.where(column.in_(list(ids)))


async def tasks(
    session: AsyncSession, *, ids: Collection[uuid.UUID] | None = None
) -> list[TaskRow]:
    """Задачи раздела — открытые и закрытые, со связями, чек-листом и переносами."""
    statement = (
        select(
            Task,
            TaskTypeRef,
            Person.full_name,
            Project.code,
            Project.title,
            Project.status_code,
            IjroAssignment.code,
        )
        .outerjoin(TaskTypeRef, TaskTypeRef.id == Task.task_type_id)
        .outerjoin(Person, Person.id == Task.assignee_person_id)
        .outerjoin(Project, Project.id == Task.project_id)
        .outerjoin(IjroAssignment, IjroAssignment.id == Task.ijro_assignment_id)
    )
    statement = _scoped(statement, Task.id, ids)

    found: dict[uuid.UUID, TaskRow] = {}
    rows = await session.execute(statement)
    for task, kind, person, project_code, project_title, project_status, ijro_code in rows:
        found[task.id] = TaskRow(
            id=task.id,
            code=task.code,
            title=task.title,
            type_code=kind.code if kind else None,
            type_names=Names.of(kind) if kind else None,
            status=task.status,
            assignee_id=task.assignee_person_id,
            assignee_name=person,
            due_at=task.due_at,
            original_due_at=task.original_due_at,
            project_id=task.project_id,
            project_code=project_code,
            project_title=project_title,
            project_status=project_status,
            ijro_id=task.ijro_assignment_id,
            ijro_code=ijro_code,
            completed_at=task.completed_at,
            created_at=task.created_at,
            description=task.description,
            version=task.version,
        )
    if not found:
        return []

    scope = None if ids is None else list(found)

    done = func.count().filter(TaskChecklistItem.is_done.is_(True))
    counts = _scoped(
        select(TaskChecklistItem.task_id, done, func.count()),
        TaskChecklistItem.task_id,
        scope,
    ).group_by(TaskChecklistItem.task_id)
    for task_id, done_count, total in await session.execute(counts):
        if task_id in found:
            found[task_id].checklist_done = done_count
            found[task_id].checklist_total = total

    # Переносы — правки срока из журнала: ключ `due_at` в изменениях. Счёт делает
    # `metrics.moves_count` тем же правилом, что «Держим ли мы свои сроки?».
    changes = _scoped(
        select(
            AuditLog.occurred_at,
            AuditLog.entity_type,
            AuditLog.entity_id,
            AuditLog.action,
            AuditLog.changes,
        ).where(
            AuditLog.entity_type == TASKS,
            AuditLog.action == AuditAction.UPDATED.value,
            AuditLog.changes.has_key("due_at"),
        ),
        AuditLog.entity_id,
        scope,
    ).order_by(AuditLog.occurred_at)
    for occurred_at, entity_type, entity_id, action, payload in await session.execute(changes):
        row = found.get(entity_id)
        if row is not None:
            row.due_changes.append(
                AuditEntry(
                    occurred_at=occurred_at,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    action=action,
                    changes=payload or {},
                )
            )
    return list(found.values())


async def checklist(session: AsyncSession, task_id: uuid.UUID) -> list[ItemRow]:
    """Пункты чек-листа в порядке, который задал человек."""
    rows = await session.scalars(
        select(TaskChecklistItem)
        .where(TaskChecklistItem.task_id == task_id)
        .order_by(TaskChecklistItem.sort_order, TaskChecklistItem.created_at)
    )
    return [
        ItemRow(id=item.id, text=item.text, is_done=item.is_done, version=item.version)
        for item in rows
    ]


async def item(
    session: AsyncSession, task_id: uuid.UUID, item_id: uuid.UUID
) -> TaskChecklistItem | None:
    """Пункт чек-листа объектом — для правки с журналом и версией."""
    found: TaskChecklistItem | None = await session.scalar(
        select(TaskChecklistItem).where(
            TaskChecklistItem.id == item_id, TaskChecklistItem.task_id == task_id
        )
    )
    return found


async def next_sort_order(session: AsyncSession, task_id: uuid.UUID) -> int:
    """Место нового пункта — в конце: пункты добавляют по ходу работы."""
    last = await session.scalar(
        select(func.max(TaskChecklistItem.sort_order)).where(TaskChecklistItem.task_id == task_id)
    )
    return (last or 0) + 1


async def task_types(session: AsyncSession) -> list[tuple[str, Names]]:
    """Действующие типы задач (ТЗ 3.9) в порядке справочника."""
    rows = await session.scalars(
        select(TaskTypeRef)
        .where(TaskTypeRef.is_active.is_(True))
        .order_by(TaskTypeRef.sort_order, TaskTypeRef.code)
    )
    return [(kind.code, Names.of(kind)) for kind in rows]


async def task_type_id(session: AsyncSession, code: str) -> uuid.UUID | None:
    """Действующий тип по коду; выключенный для новой записи не выбирается."""
    found: uuid.UUID | None = await session.scalar(
        select(TaskTypeRef.id).where(TaskTypeRef.code == code, TaskTypeRef.is_active.is_(True))
    )
    return found


async def task_type_code(session: AsyncSession, type_id: uuid.UUID) -> str | None:
    """Код типа по идентификатору — и выключенного: у старой задачи он остаётся своим."""
    found: str | None = await session.scalar(
        select(TaskTypeRef.code).where(TaskTypeRef.id == type_id)
    )
    return found


async def project_refs(session: AsyncSession) -> list[tuple[uuid.UUID, str, str]]:
    """Проекты, к которым можно привязать задачу: незакрытые, по номеру."""
    rows = await session.execute(
        select(Project.id, Project.code, Project.title)
        .where(Project.status_code.notin_(PROJECT_TERMINAL))
        .order_by(Project.code)
    )
    return list(rows.tuples().all())


async def project_is_open(session: AsyncSession, project_id: uuid.UUID) -> bool | None:
    """Открыт ли проект: `None` — такого нет, `False` — завершён или отменён."""
    status = await session.scalar(select(Project.status_code).where(Project.id == project_id))
    if status is None:
        return None
    return status not in PROJECT_TERMINAL
