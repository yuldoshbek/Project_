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

from sqlalchemy import Integer, Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import now_utc
from app.domain.comments import CommentTarget
from app.domain.dictionaries import TaskStatus
from app.domain.errors import NotFoundError
from app.domain.projects import ProgressMode, auto_progress
from app.domain.tasks import days_overdue, is_overdue, validate_transition
from app.repos.models import (
    Person,
    PriorityRef,
    Project,
    Task,
    TaskChecklistItem,
    TaskStatusRef,
)
from app.services import codes, comments

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


@dataclass(frozen=True, slots=True)
class ExportRow:
    """Строка выгрузки — уже словами, а не идентификаторами.

    Отдельный тип, а не `TaskView`: на экране исполнитель приходит идентификатором и
    интерфейс сам подставляет имя из загруженного справочника, а у файла такого
    справочника нет — его открывают в Excel, и подставить некому.
    """

    code: str
    title: str
    status: str
    priority: str
    due_at: datetime | None
    is_overdue: bool
    checklist: str
    assignee: str
    project: str


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
    planned_due_at: datetime | None = None
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
    planned_due_at: Any = _UNSET
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
        title=draft.title.strip(),
        description=draft.description,
        project_id=draft.project_id,
        assignee_person_id=draft.assignee_person_id,
        author_id=author_id,
        status=draft.status.value,
        priority_code=draft.priority_code,
        due_at=draft.due_at,
        planned_due_at=draft.planned_due_at,
        is_control=draft.is_control,
    )
    _apply_status_side_effects(task, target=draft.status, now=moment)

    await codes.add_with_code(session, task, assign=lambda: next_code(session, today=today))
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

    # Обсуждение уходит вместе с задачей. Внешним ключом это не выражается: `entity_id`
    # у комментария указывает то на задачи, то на проекты, и база такую связь не поймёт.
    await comments.delete_for(session, CommentTarget.TASK, task_id)

    await session.delete(task)
    await session.flush()
    await recalculate_project_progress(session, project_id)
    await session.flush()


@dataclass(slots=True)
class TaskFilter:
    project_id: uuid.UUID | None = None
    direction_id: uuid.UUID | None = None
    curator_person_id: uuid.UUID | None = None
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
    "planned_due_at": Task.planned_due_at,
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
        statement = statement.where(
            Task.project_id.in_(
                select(Project.id).where(Project.direction_id == filters.direction_id)
            )
        )
    if filters.curator_person_id is not None:
        # Куратор — тоже свойство проекта (ТЗ 6.2). Подзапросом, а не соединением: два
        # соединения с одной таблицей в одном запросе требуют псевдонимов, а забытый
        # псевдоним даёт не ошибку, а тихо неверную выборку.
        statement = statement.where(
            Task.project_id.in_(
                select(Project.id).where(Project.curator_person_id == filters.curator_person_id)
            )
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


async def list_for_export(
    session: AsyncSession,
    filters: TaskFilter | None = None,
    *,
    now: datetime | None = None,
    sort_by: str = "due_at",
    descending: bool = False,
) -> list[ExportRow]:
    """Задачи для выгрузки в файл.

    Отдельная функция, а не флаг у списка: у выгрузки свои колонки — названия вместо
    идентификаторов, местное время, пометка просрочки, — и подмешивать их в список для
    экрана значило бы носить их в каждом ответе API.

    Отбор здесь тот же, что на экране. Прежнее правило «не выгружать проекты, закрытые
    для показа наружу» снято вместе с признаком выдачи
    ([ADR-0024](../../../docs/adr/ADR-0024-share-externally.md)): внешних точек выдачи не
    осталось, файл открывает тот же человек, который и так видит эти задачи, и различие
    между экраном и файлом только путало.
    """
    filters = filters or TaskFilter()
    moment = now or now_utc()
    column = SORTABLE.get(sort_by, Task.due_at)

    # Названия подставляются здесь, а не собираются читающим кодом: файл открывают в
    # Excel, и идентификатор в колонке «Исполнитель» не значит для человека ничего.
    statement = (
        _apply(
            select(Task, TaskStatusRef.name_ru, PriorityRef.name_ru, Person.full_name, Project),
            filters,
            now=moment,
        )
        .outerjoin(TaskStatusRef, TaskStatusRef.code == Task.status)
        .outerjoin(PriorityRef, PriorityRef.code == Task.priority_code)
        .outerjoin(Person, Person.id == Task.assignee_person_id)
        .outerjoin(Project, Project.id == Task.project_id)
    )
    order = column.desc() if descending else column.asc()
    if column is Task.due_at:
        order = order.nullslast()

    rows = list(await session.execute(statement.order_by(order)))

    # Прогресс чек-листа — одним запросом на всю выгрузку, а не по запросу на строку:
    # выгружают сотни задач, и запрос на каждую превратил бы файл в минуту ожидания.
    counts = await _checklist_counts(session, [row[0].id for row in rows])

    return [
        ExportRow(
            code=task.code,
            title=task.title,
            status=status_name or task.status,
            priority=priority_name or task.priority_code,
            due_at=task.due_at,
            is_overdue=view(task, now=moment).is_overdue,
            checklist=_checklist_cell(counts.get(task.id)),
            assignee=assignee_name or "",
            project="" if project is None else f"{project.code} {project.title}",
        )
        for task, status_name, priority_name, assignee_name, project in rows
    ]


async def _checklist_counts(
    session: AsyncSession, task_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    if not task_ids:
        return {}

    done = func.sum(case((TaskChecklistItem.is_done, 1), else_=0)).cast(Integer)
    rows = await session.execute(
        select(TaskChecklistItem.task_id, done, func.count())
        .where(TaskChecklistItem.task_id.in_(task_ids))
        .group_by(TaskChecklistItem.task_id)
    )
    return {task_id: (int(done_count or 0), int(total)) for task_id, done_count, total in rows}


def _checklist_cell(counts: tuple[int, int] | None) -> str:
    """«3 из 5» или пусто.

    Пусто, а не «0 из 0»: задача без чек-листа — не задача, в которой ничего не сделано.
    В колонке Excel эта разница видна сразу, а «0 из 0» в сотне строк — это шум, по
    которому нельзя отсортировать и в котором тонут те, у кого чек-лист есть.
    """
    if counts is None:
        return ""
    done, total = counts
    return f"{done} из {total}"
