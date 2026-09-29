"""Read-модель Управления: обход, справочники с числом ссылок, шаблоны вех, доступ.

Число запросов не зависит от числа записей — по одному на признак (CLAUDE.md, «Read-модель
на экран»). Просроченное берётся у Календаря (`repos.calendar.overdue`): «срок прошёл» —
одно правило на оба экрана. Здесь только чтение; ступени и пороги считает
`app.services.metrics`.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit import AuditAction
from app.domain.dictionaries import ProjectStatus, TaskStatus
from app.domain.management import DictionaryKind
from app.domain.pult import TASKS
from app.repos.models import (
    AccessLink,
    AuditLog,
    Direction,
    IjroAssignment,
    Organization,
    Person,
    Project,
    ProjectOrganization,
    ProjectStatusRef,
    ProjectTypeMilestone,
    ProjectTypeRef,
    Region,
    RoundMark,
    Session,
    Setting,
    Task,
    TaskStatusRef,
    TaskTypeRef,
    User,
)
from app.repos.models.dictionaries import DictionaryEntry

PROJECT_TERMINAL = [status.value for status in ProjectStatus if status.is_terminal]
TASK_TERMINAL = [status.value for status in TaskStatus if status.is_terminal]

ENTRY_MODELS: dict[DictionaryKind, type[DictionaryEntry]] = {
    DictionaryKind.PROJECT_TYPES: ProjectTypeRef,
    DictionaryKind.TASK_TYPES: TaskTypeRef,
    DictionaryKind.DIRECTIONS: Direction,
    DictionaryKind.REGIONS: Region,
    DictionaryKind.PROJECT_STATUSES: ProjectStatusRef,
    DictionaryKind.TASK_STATUSES: TaskStatusRef,
}


def _open_project() -> Any:
    """Задача вне проекта или в незакрытом: у закрытого проекта работа закрыта вместе с ним."""
    return or_(Task.project_id.is_(None), Project.status_code.notin_(PROJECT_TERMINAL))


# --------------------------------------------------------------------------------------
# Обход
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TaskRow:
    id: uuid.UUID
    title: str
    status: str
    version: int
    project_title: str | None
    assignee_name: str | None
    since: datetime
    """С какого момента задача в этом состоянии: на проверке или без ответственного."""


def _task_select(*extra: Any) -> Select[Any]:
    return (
        select(
            Task.id,
            Task.title,
            Task.status,
            Task.version,
            Project.title,
            Person.full_name,
            Task.created_at,
            *extra,
        )
        .outerjoin(Project, Project.id == Task.project_id)
        .outerjoin(Person, Person.id == Task.assignee_person_id)
        .where(Task.status.notin_(TASK_TERMINAL), _open_project())
    )


async def _last_change(
    session: AsyncSession, ids: Collection[uuid.UUID], condition: Any
) -> dict[uuid.UUID, datetime]:
    """Когда в журнале последний раз случилась правка задачи, подходящая под условие."""
    if not ids:
        return {}
    rows = await session.execute(
        select(AuditLog.entity_id, func.max(AuditLog.occurred_at))
        .where(
            AuditLog.entity_type == TASKS,
            AuditLog.action == AuditAction.UPDATED.value,
            AuditLog.entity_id.in_(list(ids)),
            condition,
        )
        .group_by(AuditLog.entity_id)
    )
    return dict(rows.tuples().all())


async def in_review(session: AsyncSession) -> list[TaskRow]:
    """Задачи на проверке и когда они туда перешли — по журналу изменений.

    Перехода в журнале нет, если задачу завели сразу в этом статусе, — тогда отсчёт от
    создания: ничего раньше задача и не делала.
    """
    rows = list(
        (await session.execute(_task_select().where(Task.status == TaskStatus.IN_REVIEW.value)))
        .tuples()
        .all()
    )
    entered = await _last_change(
        session,
        [row[0] for row in rows],
        AuditLog.changes["status"]["to"].astext == TaskStatus.IN_REVIEW.value,
    )
    return [
        TaskRow(
            id=task_id,
            title=title,
            status=status,
            version=version,
            project_title=project_title,
            assignee_name=assignee,
            since=entered.get(task_id, created_at),
        )
        for task_id, title, status, version, project_title, assignee, created_at in rows
    ]


async def unassigned(session: AsyncSession) -> list[TaskRow]:
    """Открытые задачи без ответственного и с какого момента: с создания или с правки,
    которая его сняла. Снятие удалением сотрудника журнала не оставляет — тогда от создания.
    """
    rows = list(
        (await session.execute(_task_select().where(Task.assignee_person_id.is_(None))))
        .tuples()
        .all()
    )
    cleared = await _last_change(
        session,
        [row[0] for row in rows],
        AuditLog.changes.has_key("assignee_person_id")
        & AuditLog.changes["assignee_person_id"]["to"].astext.is_(None),
    )
    return [
        TaskRow(
            id=task_id,
            title=title,
            status=status,
            version=version,
            project_title=project_title,
            assignee_name=assignee,
            since=max(created_at, cleared.get(task_id, created_at)),
        )
        for task_id, title, status, version, project_title, assignee, created_at in rows
    ]


@dataclass(frozen=True, slots=True)
class ImpedimentRow:
    id: uuid.UUID
    title: str
    version: int
    responsible_name: str | None
    noted_at: datetime
    """Когда «что мешает» записали или подтвердили; без отметки — последняя правка проекта."""


async def impediments(session: AsyncSession) -> list[ImpedimentRow]:
    """Незакрытые проекты с записью «что мешает». Устаревшие отбирает правило порога."""
    rows = await session.execute(
        select(
            Project.id,
            Project.title,
            Project.version,
            Person.full_name,
            func.coalesce(Project.impediment_updated_at, Project.updated_at, Project.created_at),
        )
        .outerjoin(Person, Person.id == Project.responsible_person_id)
        .where(
            Project.status_code.notin_(PROJECT_TERMINAL),
            Project.impediment.is_not(None),
            func.btrim(Project.impediment) != "",
        )
    )
    return [
        ImpedimentRow(id=pid, title=title, version=version, responsible_name=name, noted_at=noted)
        for pid, title, version, name, noted in rows.tuples()
    ]


async def versions(
    session: AsyncSession, model: Any, ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Версии записей — пункт обхода несёт версию той, что меняет его действие (инвариант 15)."""
    if not ids:
        return {}
    rows = await session.execute(select(model.id, model.version).where(model.id.in_(list(ids))))
    return dict(rows.tuples().all())


async def task_states(
    session: AsyncSession, ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, int]]:
    """Статус и версия задач: у новой задачи в обходе нет «сделана» (граф переходов)."""
    if not ids:
        return {}
    rows = await session.execute(
        select(Task.id, Task.status, Task.version).where(Task.id.in_(list(ids)))
    )
    return {task_id: (status, version) for task_id, status, version in rows.tuples()}


async def done_since(session: AsyncSession, since: datetime) -> int:
    """Действий обхода с понедельника — «сделано на неделе»."""
    found = await session.scalar(
        select(func.count()).select_from(RoundMark).where(RoundMark.created_at >= since)
    )
    return found or 0


# --------------------------------------------------------------------------------------
# Справочники
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EntryRow:
    id: uuid.UUID
    name: str
    is_active: bool
    version: int
    org_kind: str | None = None
    is_center: bool = False


async def entries(session: AsyncSession) -> dict[DictionaryKind, list[EntryRow]]:
    """Значения всех справочников — в порядке форм; организации — по названию."""
    found: dict[DictionaryKind, list[EntryRow]] = {}
    for kind, model in ENTRY_MODELS.items():
        rows = await session.scalars(select(model).order_by(model.sort_order, model.name_ru))
        found[kind] = [
            EntryRow(id=row.id, name=row.name_ru, is_active=row.is_active, version=row.version)
            for row in rows
        ]
    organizations = await session.scalars(select(Organization).order_by(Organization.name))
    found[DictionaryKind.ORGANIZATIONS] = [
        EntryRow(
            id=row.id,
            name=row.name,
            is_active=row.is_active,
            version=row.version,
            org_kind=row.kind,
            is_center=row.is_founded_by_agency,
        )
        for row in organizations
    ]
    return found


async def _counts(session: AsyncSession, column: Any) -> dict[Any, int]:
    rows = await session.execute(
        select(column, func.count()).where(column.is_not(None)).group_by(column)
    )
    return dict(rows.tuples().all())


async def used(session: AsyncSession) -> dict[DictionaryKind, dict[uuid.UUID, int]]:
    """Сколько записей ссылается на каждое значение — ответ на «можно ли выключить».

    Статусы связаны с записями по коду, остальное — по идентификатору. Организацию держат
    роли в проектах и головное исполнение поручений.
    """
    status_ids = dict(
        (await session.execute(select(ProjectStatusRef.code, ProjectStatusRef.id))).tuples().all()
    )
    task_status_ids = dict(
        (await session.execute(select(TaskStatusRef.code, TaskStatusRef.id))).tuples().all()
    )
    by_code_projects = await _counts(session, Project.status_code)
    by_code_tasks = await _counts(session, Task.status)
    organizations = await _counts(session, ProjectOrganization.organization_id)
    for org_id, count in (await _counts(session, IjroAssignment.lead_organization_id)).items():
        organizations[org_id] = organizations.get(org_id, 0) + count
    return {
        DictionaryKind.PROJECT_TYPES: await _counts(session, Project.project_type_id),
        DictionaryKind.TASK_TYPES: await _counts(session, Task.task_type_id),
        DictionaryKind.DIRECTIONS: await _counts(session, Project.direction_id),
        DictionaryKind.REGIONS: await _counts(session, Project.region_id),
        DictionaryKind.PROJECT_STATUSES: {
            status_ids[code]: count
            for code, count in by_code_projects.items()
            if code in status_ids
        },
        DictionaryKind.TASK_STATUSES: {
            task_status_ids[code]: count
            for code, count in by_code_tasks.items()
            if code in task_status_ids
        },
        DictionaryKind.ORGANIZATIONS: organizations,
    }


@dataclass(frozen=True, slots=True)
class StepRow:
    id: uuid.UUID
    name: str
    offset_days: int
    version: int


async def template_steps(session: AsyncSession) -> dict[uuid.UUID, list[StepRow]]:
    """Шаблоны вех всех типов проектов — по сроку от начала, как их получит новый проект."""
    found: dict[uuid.UUID, list[StepRow]] = {
        type_id: [] for type_id in await session.scalars(select(ProjectTypeRef.id))
    }
    rows = await session.scalars(
        select(ProjectTypeMilestone).order_by(
            ProjectTypeMilestone.offset_days, ProjectTypeMilestone.sort_order
        )
    )
    for step in rows:
        found.setdefault(step.project_type_id, []).append(
            StepRow(
                id=step.id, name=step.name_ru, offset_days=step.offset_days, version=step.version
            )
        )
    return found


# --------------------------------------------------------------------------------------
# Доступ
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LinkRow:
    role: str
    issued_at: datetime | None
    last_login_at: datetime | None


async def links(session: AsyncSession) -> list[LinkRow]:
    """Когда выпущена ссылка и когда входили последний раз — по ролям (ТЗ 3.8).

    Последний вход — по всем сессиям, и погашенным, и истёкшим: перевыпуск гасит сессии, но
    не стирает их (`services.access.revoke_sessions`), и «когда он заходил» переживает его.
    """
    last_seen = (
        select(Session.user_id, func.max(Session.last_seen_at).label("seen"))
        .group_by(Session.user_id)
        .subquery()
    )
    rows = await session.execute(
        select(User.role, AccessLink.issued_at, last_seen.c.seen)
        .outerjoin(AccessLink, AccessLink.user_id == User.id)
        .outerjoin(last_seen, last_seen.c.user_id == User.id)
        .where(User.is_active.is_(True))
        .order_by(User.role)
    )
    return [
        LinkRow(role=role, issued_at=issued, last_login_at=seen)
        for role, issued, seen in rows.tuples()
    ]


# --------------------------------------------------------------------------------------
# Для записи: объекты, которые правит сервис
# --------------------------------------------------------------------------------------


async def settings(session: AsyncSession) -> list[Setting]:
    """Пороги объектами — со значением, границами и версией."""
    return list(await session.scalars(select(Setting).order_by(Setting.key)))


async def setting(session: AsyncSession, key: str) -> Setting | None:
    found: Setting | None = await session.scalar(select(Setting).where(Setting.key == key))
    return found


async def ordered(session: AsyncSession, model: type[DictionaryEntry]) -> list[DictionaryEntry]:
    """Значения справочника в порядке форм — соседи для «выше» и «ниже»."""
    return list(await session.scalars(select(model).order_by(model.sort_order, model.name_ru)))


async def last_sort_order(session: AsyncSession, column: Any, *condition: Any) -> int:
    found = await session.scalar(select(func.max(column)).where(*condition))
    return int(found or 0)


async def name_taken(
    session: AsyncSession, column: Any, name: str, *, exclude: uuid.UUID | None, id_column: Any
) -> bool:
    """Такое название уже есть — без учёта регистра: «Прочее» и «прочее» — одно значение."""
    statement = select(func.count()).where(func.lower(column) == name.lower())
    if exclude is not None:
        statement = statement.where(id_column != exclude)
    return bool(await session.scalar(statement))
