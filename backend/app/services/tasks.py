"""Задачи: сценарии использования.

Просрочка не хранится и здесь не записывается: она считается на выдаче
([ADR-0004](../../../docs/adr/ADR-0004-overdue-is-computed.md)). Фильтр «просроченные»
при этом идёт в SQL, а не в память: он самый частый на дашборде, и обходить ради него
все задачи означало бы платить полным перебором за каждый взгляд на экран.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import now_utc
from app.domain.dictionaries import TaskStatus
from app.domain.errors import NotFoundError
from app.domain.projects import ProgressMode, auto_progress
from app.domain.tasks import days_overdue, is_overdue, validate_transition
from app.repos.models import Project, Task
from app.services import codes

CODE_PREFIX = "TSK"
CODE_DIGITS = 5

_UNSET: Any = object()
"""Отличает «поле не прислали» от «поле обнулили» — как в проектах."""

TERMINAL = [status.value for status in TaskStatus if status.is_terminal]


def overdue_condition(now: datetime) -> Any:
    """Просрочка на языке базы — то же правило, что `is_overdue` в домене (ADR-0004).

    Правило записано на двух языках, и это неизбежно: фильтр «просроченные» самый частый
    на дашборде, а считать его в памяти значит обходить все задачи при каждом взгляде на
    экран. Но записано оно по одному разу на язык и берётся отсюда — дашбордом, сигналами
    проекта и списком задач. Совпадение двух записей закреплено тестом, который сверяет
    отфильтрованный список с посчитанным признаком: без него они однажды разойдутся, и
    цифры на двух экранах перестанут сходиться.
    """
    return (Task.due_at.is_not(None)) & (Task.due_at < now) & (Task.status.notin_(TERMINAL))


@dataclass(frozen=True, slots=True)
class TaskView:
    """Задача вместе с тем, что о ней вычислено."""

    task: Task
    is_overdue: bool
    days_overdue: int


def view(task: Task, *, now: datetime) -> TaskView:
    status = TaskStatus(task.status)
    return TaskView(
        task=task,
        is_overdue=is_overdue(due_at=task.due_at, status=status, now=now),
        days_overdue=days_overdue(due_at=task.due_at, status=status, now=now),
    )


@dataclass(slots=True)
class TaskDraft:
    title: str
    priority_code: str
    status: TaskStatus = TaskStatus.NEW
    project_id: uuid.UUID | None = None
    description: str | None = None
    assignee_person_id: uuid.UUID | None = None
    due_at: datetime | None = None
    is_control: bool = False


@dataclass(slots=True)
class TaskPatch:
    title: Any = _UNSET
    description: Any = _UNSET
    project_id: Any = _UNSET
    assignee_person_id: Any = _UNSET
    status: Any = _UNSET
    priority_code: Any = _UNSET
    due_at: Any = _UNSET
    is_control: Any = _UNSET

    def assigned(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__slots__
            if getattr(self, name) is not _UNSET
        }


async def next_code(session: AsyncSession, *, today: date) -> str:
    """Следующий человекочитаемый номер задачи: TSK-2026-00123."""
    return await codes.next_code(
        session, column=Task.code, prefix=CODE_PREFIX, digits=CODE_DIGITS, today=today
    )


def _apply_status_side_effects(task: Task, *, target: TaskStatus, now: datetime) -> None:
    """Отметки времени ставит система, а не пользователь.

    Спрашивать у помощника, когда именно задача пошла в работу, — лишний ввод, а
    незаполненные им отметки сделали бы бесполезной всю статистику по срокам.
    """
    if target is TaskStatus.IN_PROGRESS and task.started_at is None:
        task.started_at = now
    if target is TaskStatus.DONE:
        task.completed_at = now
    else:
        # Переоткрыли — отметка о выполнении снимается: иначе задача остаётся
        # выполненной в отчётах и незакрытой на экране одновременно.
        task.completed_at = None


async def recalculate_project_progress(session: AsyncSession, project_id: uuid.UUID | None) -> None:
    """Пересчитывает процент выполнения проекта в режиме `auto`.

    Перенесено из ORB-011: там расчёт был написан, но подключать его было не к чему.
    В ручном режиме значение не трогается — иначе цифра куратора молча затиралась бы
    после каждой закрытой задачи.
    """
    if project_id is None:
        return

    project = await session.get(Project, project_id)
    if project is None or project.progress_mode != ProgressMode.AUTO.value:
        return

    counts = await session.execute(
        select(
            func.count(),
            func.count().filter(Task.status == TaskStatus.DONE.value),
        ).where(Task.project_id == project_id)
    )
    total, done = counts.one()
    project.progress_pct = auto_progress(total_tasks=total, done_tasks=done)


async def create(
    session: AsyncSession,
    draft: TaskDraft,
    *,
    author_id: uuid.UUID | None,
    today: date,
    now: datetime | None = None,
) -> Task:
    moment = now or now_utc()
    task = Task(
        code=await next_code(session, today=today),
        title=draft.title.strip(),
        description=draft.description,
        project_id=draft.project_id,
        assignee_person_id=draft.assignee_person_id,
        author_id=author_id,
        status=draft.status.value,
        priority_code=draft.priority_code,
        due_at=draft.due_at,
        is_control=draft.is_control,
    )
    _apply_status_side_effects(task, target=draft.status, now=moment)

    session.add(task)
    await session.flush()
    await recalculate_project_progress(session, task.project_id)
    await session.flush()
    return task


async def get(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFoundError("Задача не найдена")
    return task


async def update(
    session: AsyncSession,
    task_id: uuid.UUID,
    patch: TaskPatch,
    *,
    now: datetime | None = None,
) -> Task:
    task = await get(session, task_id)
    moment = now or now_utc()
    changes = patch.assigned()
    previous_project = task.project_id

    if "status" in changes:
        target = TaskStatus(changes["status"])
        validate_transition(current=TaskStatus(task.status), target=target)
        _apply_status_side_effects(task, target=target, now=moment)

    for name, value in changes.items():
        setattr(task, name, value.value if isinstance(value, Enum) else value)

    await session.flush()

    # Пересчитываются оба проекта: и тот, откуда задачу забрали, и тот, куда положили.
    # Иначе у прежнего процент остаётся посчитанным по задаче, которой у него нет.
    await recalculate_project_progress(session, previous_project)
    if task.project_id != previous_project:
        await recalculate_project_progress(session, task.project_id)
    await session.flush()
    return task


async def delete(session: AsyncSession, task_id: uuid.UUID) -> None:
    task = await get(session, task_id)
    project_id = task.project_id
    await session.delete(task)
    await session.flush()
    await recalculate_project_progress(session, project_id)
    await session.flush()


@dataclass(slots=True)
class TaskFilter:
    project_id: uuid.UUID | None = None
    direction_id: uuid.UUID | None = None
    assignee_person_id: uuid.UUID | None = None
    status: TaskStatus | None = None
    priority_code: str | None = None
    is_control: bool | None = None
    overdue: bool | None = None
    without_project: bool | None = None
    search: str | None = None
    due_before: datetime | None = None


SORTABLE = {
    "code": Task.code,
    "title": Task.title,
    "due_at": Task.due_at,
    "status": Task.status,
    "created_at": Task.created_at,
}


def _apply(statement: Select[Any], filters: TaskFilter, *, now: datetime) -> Select[Any]:
    if filters.project_id is not None:
        statement = statement.where(Task.project_id == filters.project_id)
    if filters.without_project:
        statement = statement.where(Task.project_id.is_(None))
    if filters.direction_id is not None:
        # Направление принадлежит проекту, а не задаче: дублировать его в задаче значило
        # бы завести второй источник правды и рассинхронизировать их при переносе задачи.
        statement = statement.join(Project, Task.project_id == Project.id).where(
            Project.direction_id == filters.direction_id
        )
    if filters.assignee_person_id is not None:
        statement = statement.where(Task.assignee_person_id == filters.assignee_person_id)
    if filters.status is not None:
        statement = statement.where(Task.status == filters.status.value)
    if filters.priority_code is not None:
        statement = statement.where(Task.priority_code == filters.priority_code)
    if filters.is_control is not None:
        statement = statement.where(Task.is_control.is_(filters.is_control))
    if filters.due_before is not None:
        statement = statement.where(Task.due_at < filters.due_before)
    if filters.search:
        statement = statement.where(Task.title.ilike(f"%{filters.search.strip()}%"))

    if filters.overdue is not None:
        condition = overdue_condition(now)
        statement = statement.where(condition if filters.overdue else ~condition)

    return statement


async def list_tasks(
    session: AsyncSession,
    filters: TaskFilter | None = None,
    *,
    now: datetime | None = None,
    sort_by: str = "due_at",
    descending: bool = False,
) -> list[TaskView]:
    """Задачи вместе с вычисленной просрочкой.

    Задачи без срока при сортировке по сроку уходят в конец в обоих направлениях: у них
    срока нет, и ставить их впереди горящих — значит прятать горящие.
    """
    filters = filters or TaskFilter()
    moment = now or now_utc()
    column = SORTABLE.get(sort_by, Task.due_at)

    statement = _apply(select(Task), filters, now=moment)
    order = column.desc() if descending else column.asc()
    if column is Task.due_at:
        order = order.nullslast()
    statement = statement.order_by(order)

    return [view(task, now=moment) for task in await session.scalars(statement)]
