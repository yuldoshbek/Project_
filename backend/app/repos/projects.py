"""Read-модель раздела «Проекты»: всё, из чего собираются плитка, строка и карточка.

Число запросов не зависит от числа проектов — по одному на признак: сами проекты, вехи,
задачи, организации, подпроекты, переносы. Запрос на проект превратил бы список из
двухсот строк в тысячу обращений к базе (CLAUDE.md, «Read-модель на экран»).

Здесь только чтение и то, что нужно для записи: объекты, которые сервис правит. Числа —
готовность, отставание, ступень — считает `app.services.metrics`, а не этот модуль.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.audit import AuditAction
from app.domain.dictionaries import OrganizationRole, TaskStatus
from app.domain.pult import PROJECTS, AuditEntry
from app.repos.models import (
    AuditLog,
    Direction,
    Milestone,
    Organization,
    Person,
    Project,
    ProjectOrganization,
    ProjectTypeMilestone,
    ProjectTypeRef,
    Region,
    Task,
)


@dataclass(frozen=True, slots=True)
class Names:
    """Название справочника на трёх письменностях — выбирает сервис по языку."""

    ru: str
    uz_cyrl: str
    uz_latn: str

    @classmethod
    def of(cls, entry: Any) -> Names:
        return cls(ru=entry.name_ru, uz_cyrl=entry.name_uz_cyrl, uz_latn=entry.name_uz_latn)


@dataclass(frozen=True, slots=True)
class MarkRow:
    id: uuid.UUID
    title: str
    due_on: date
    original_due_on: date
    is_passed: bool
    passed_on: date | None
    version: int


@dataclass(slots=True)
class ProjectRow:
    """Проект со всем, что показывает раздел, — без вычисленных чисел."""

    id: uuid.UUID
    code: str
    title: str
    type_code: str
    type_names: Names
    status: str
    status_reason: str | None
    parent_id: uuid.UUID | None
    parent_title: str | None
    is_multiyear: bool
    started_on: date
    due_on: date
    original_due_on: date
    responsible_id: uuid.UUID | None
    responsible_name: str | None
    impediment: str | None
    impediment_updated_at: datetime | None
    changed_at: datetime
    """Последняя правка самой записи — дата «что мешает», если своей даты у строки нет."""

    version: int
    description: str | None
    direction: Names | None
    region: Names | None
    subprojects: int = 0
    marks: list[MarkRow] = field(default_factory=list)
    done_tasks: int = 0
    total_tasks: int = 0
    center_role: str | None = None
    lead_outside: bool = False
    due_changes: list[AuditEntry] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TemplateStep:
    names: Names
    offset_days: int
    sort_order: int


@dataclass(frozen=True, slots=True)
class TypeRow:
    id: uuid.UUID
    code: str
    names: Names
    template: tuple[TemplateStep, ...]


@dataclass(frozen=True, slots=True)
class OrganizationRow:
    id: uuid.UUID
    name: str
    role: str
    is_center: bool


@dataclass(frozen=True, slots=True)
class TaskRow:
    id: uuid.UUID
    title: str
    status: str
    due_at: datetime | None
    assignee_id: uuid.UUID | None
    assignee_name: str | None


def _scoped(statement: Select[Any], column: Any, ids: Collection[uuid.UUID] | None) -> Select[Any]:
    """Ограничить запрос нужными проектами. Весь список — без `IN` на двести значений."""
    return statement if ids is None else statement.where(column.in_(list(ids)))


async def projects(
    session: AsyncSession,
    *,
    ids: Collection[uuid.UUID] | None = None,
    parent_id: uuid.UUID | None = None,
) -> list[ProjectRow]:
    """Проекты раздела с вехами, счётом задач, ролями организаций и переносами.

    `ids` — только эти проекты; `parent_id` — подпроекты программы. Ни того, ни другого —
    весь портфель: раздел показывает и завершённые, и отменённые, в отличие от Пульта.
    """
    parent = aliased(Project)
    statement = (
        select(Project, ProjectTypeRef, parent.title, Person.full_name, Direction, Region)
        .join(ProjectTypeRef, ProjectTypeRef.id == Project.project_type_id)
        .outerjoin(parent, parent.id == Project.parent_project_id)
        .outerjoin(Person, Person.id == Project.responsible_person_id)
        .outerjoin(Direction, Direction.id == Project.direction_id)
        .outerjoin(Region, Region.id == Project.region_id)
    )
    statement = _scoped(statement, Project.id, ids)
    if parent_id is not None:
        statement = statement.where(Project.parent_project_id == parent_id)

    found: dict[uuid.UUID, ProjectRow] = {}
    for project, kind, parent_title, person_name, direction, region in await session.execute(
        statement
    ):
        found[project.id] = ProjectRow(
            id=project.id,
            code=project.code,
            title=project.title,
            type_code=kind.code,
            type_names=Names.of(kind),
            status=project.status_code,
            status_reason=project.status_reason,
            parent_id=project.parent_project_id,
            parent_title=parent_title,
            is_multiyear=project.is_multiyear,
            started_on=project.started_on,
            due_on=project.due_on,
            original_due_on=project.original_due_on,
            responsible_id=project.responsible_person_id,
            responsible_name=person_name,
            impediment=project.impediment,
            impediment_updated_at=project.impediment_updated_at,
            changed_at=project.updated_at or project.created_at,
            version=project.version,
            description=project.description,
            direction=Names.of(direction) if direction else None,
            region=Names.of(region) if region else None,
        )
    if not found:
        return []

    # Дальше — по уже найденным: весь портфель без фильтра, выборка — по списку.
    scope = None if ids is None and parent_id is None else list(found)
    await _subprojects(session, found, scope)
    await _milestones(session, found, scope)
    await _tasks(session, found, scope)
    await _organizations(session, found, scope)
    await _due_changes(session, found, scope)
    return list(found.values())


async def _subprojects(
    session: AsyncSession, found: dict[uuid.UUID, ProjectRow], scope: list[uuid.UUID] | None
) -> None:
    statement = _scoped(
        select(Project.parent_project_id, func.count()).where(
            Project.parent_project_id.is_not(None)
        ),
        Project.parent_project_id,
        scope,
    ).group_by(Project.parent_project_id)
    for parent_id, count in await session.execute(statement):
        if parent_id in found:
            found[parent_id].subprojects = count


async def _milestones(
    session: AsyncSession, found: dict[uuid.UUID, ProjectRow], scope: list[uuid.UUID] | None
) -> None:
    # Порядок вех задаёт человек, а не дата (`Milestone.sort_order`); дата — только при
    # равном порядке, иначе два шаблонных шага на одном месте менялись бы местами.
    statement = _scoped(
        select(Milestone).order_by(Milestone.sort_order, Milestone.due_on, Milestone.title),
        Milestone.project_id,
        scope,
    )
    for mark in await session.scalars(statement):
        if mark.project_id in found:
            found[mark.project_id].marks.append(
                MarkRow(
                    id=mark.id,
                    title=mark.title,
                    due_on=mark.due_on,
                    original_due_on=mark.original_due_on,
                    is_passed=mark.is_passed,
                    passed_on=mark.passed_on,
                    version=mark.version,
                )
            )


async def _tasks(
    session: AsyncSession, found: dict[uuid.UUID, ProjectRow], scope: list[uuid.UUID] | None
) -> None:
    # Отменённая задача не входит в счёт: её не сделают, и в знаменателе готовности она
    # навсегда держала бы проект недоделанным.
    done = func.count().filter(Task.status == TaskStatus.DONE.value)
    counted = func.count().filter(Task.status != TaskStatus.CANCELLED.value)
    statement = _scoped(
        select(Task.project_id, done, counted).where(Task.project_id.is_not(None)),
        Task.project_id,
        scope,
    ).group_by(Task.project_id)
    for project_id, done_count, total in await session.execute(statement):
        if project_id in found:
            found[project_id].done_tasks = done_count
            found[project_id].total_tasks = total


async def _organizations(
    session: AsyncSession, found: dict[uuid.UUID, ProjectRow], scope: list[uuid.UUID] | None
) -> None:
    statement = _scoped(
        select(
            ProjectOrganization.project_id,
            ProjectOrganization.role,
            Organization.is_founded_by_agency,
        ).join(Organization, Organization.id == ProjectOrganization.organization_id),
        ProjectOrganization.project_id,
        scope,
    )
    for project_id, role, is_center in await session.execute(statement):
        row = found.get(project_id)
        if row is None:
            continue
        if is_center:
            # Роль Центра — основа среза «что держит Центр» (ТЗ 5). У Центра в проекте
            # одна роль: уникальность пары «проект + организация» держит база.
            row.center_role = role
        elif role == OrganizationRole.LEAD_AGENCY.value:
            # Первая половина «зависит от чужих» — то же правило, что у лестницы
            # (`app.repos.attention._outside_lead_projects`).
            row.lead_outside = True


async def _due_changes(
    session: AsyncSession, found: dict[uuid.UUID, ProjectRow], scope: list[uuid.UUID] | None
) -> None:
    """Правки срока проектов из журнала — из них сервис считает переносы.

    Только записи, где менялся срок: ключ `due_on` в изменениях. Индекс журнала по
    «раздел + запись» делает этот запрос дешёвым и на годовом журнале.
    """
    statement = _scoped(
        select(
            AuditLog.occurred_at,
            AuditLog.entity_type,
            AuditLog.entity_id,
            AuditLog.action,
            AuditLog.changes,
        ).where(
            AuditLog.entity_type == PROJECTS,
            AuditLog.action == AuditAction.UPDATED.value,
            AuditLog.changes.has_key("due_on"),
        ),
        AuditLog.entity_id,
        scope,
    ).order_by(AuditLog.occurred_at)
    for occurred_at, entity_type, entity_id, action, changes in await session.execute(statement):
        row = found.get(entity_id)
        if row is not None:
            row.due_changes.append(
                AuditEntry(
                    occurred_at=occurred_at,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    action=action,
                    changes=changes or {},
                )
            )


async def project_types(
    session: AsyncSession, *, codes: Collection[str] | None = None
) -> list[TypeRow]:
    """Действующие типы проектов с шаблонами вех — для формы нового проекта (ТЗ 3.1).

    Выключенный тип сюда не попадает и по коду: завести по нему новый проект нельзя, а
    старые проекты показывают его название из своей строки, не отсюда.
    """
    statement = (
        select(ProjectTypeRef)
        .where(ProjectTypeRef.is_active.is_(True))
        .order_by(ProjectTypeRef.sort_order, ProjectTypeRef.code)
    )
    if codes is not None:
        statement = statement.where(ProjectTypeRef.code.in_(list(codes)))
    kinds = list(await session.scalars(statement))
    if not kinds:
        return []

    steps: dict[uuid.UUID, list[TemplateStep]] = {kind.id: [] for kind in kinds}
    for step in await session.scalars(
        select(ProjectTypeMilestone)
        .where(ProjectTypeMilestone.project_type_id.in_(list(steps)))
        .order_by(ProjectTypeMilestone.sort_order)
    ):
        steps[step.project_type_id].append(
            TemplateStep(
                names=Names.of(step), offset_days=step.offset_days, sort_order=step.sort_order
            )
        )
    return [
        TypeRow(id=kind.id, code=kind.code, names=Names.of(kind), template=tuple(steps[kind.id]))
        for kind in kinds
    ]


async def people(session: AsyncSession) -> list[tuple[uuid.UUID, str]]:
    """Кого можно назначить ответственным: действующие сотрудники по алфавиту."""
    rows = await session.execute(
        select(Person.id, Person.full_name)
        .where(Person.is_active.is_(True))
        .order_by(Person.full_name)
    )
    return list(rows.tuples().all())


async def person_is_active(session: AsyncSession, person_id: uuid.UUID) -> bool:
    return bool(
        await session.scalar(
            select(Person.id).where(Person.id == person_id, Person.is_active.is_(True))
        )
    )


async def organizations(session: AsyncSession, project_id: uuid.UUID) -> list[OrganizationRow]:
    """Организации проекта с ролями. Центр — первым: ради него срез и заводился."""
    rows = await session.execute(
        select(
            Organization.id,
            func.coalesce(Organization.short_name, Organization.name),
            ProjectOrganization.role,
            Organization.is_founded_by_agency,
        )
        .join(Organization, Organization.id == ProjectOrganization.organization_id)
        .where(ProjectOrganization.project_id == project_id)
        .order_by(Organization.is_founded_by_agency.desc(), Organization.name)
    )
    return [
        OrganizationRow(id=org_id, name=name, role=role, is_center=is_center)
        for org_id, name, role, is_center in rows
    ]


async def tasks(session: AsyncSession, project_id: uuid.UUID) -> list[TaskRow]:
    """Задачи проекта: открытые по сроку, закрытые в конце."""
    terminal = [status.value for status in TaskStatus if status.is_terminal]
    rows = await session.execute(
        select(
            Task.id, Task.title, Task.status, Task.due_at, Task.assignee_person_id, Person.full_name
        )
        .outerjoin(Person, Person.id == Task.assignee_person_id)
        .where(Task.project_id == project_id)
        .order_by(Task.status.in_(terminal), Task.due_at.asc().nulls_last(), Task.code)
    )
    return [
        TaskRow(
            id=task_id,
            title=title,
            status=status,
            due_at=due_at,
            assignee_id=assignee_id,
            assignee_name=assignee_name,
        )
        for task_id, title, status, due_at, assignee_id, assignee_name in rows
    ]


async def milestones_of(
    session: AsyncSession, project_id: uuid.UUID, ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, Milestone]:
    """Вехи проекта для правки срока — объектами: правка мимо ORM обходит журнал и версию."""
    if not ids:
        return {}
    rows = await session.scalars(
        select(Milestone).where(Milestone.project_id == project_id, Milestone.id.in_(list(ids)))
    )
    return {mark.id: mark for mark in rows}
