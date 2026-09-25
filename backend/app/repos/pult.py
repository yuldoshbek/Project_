"""Read-модель Пульта: всё, что экран показывает рядом с числами лестницы.

Числа — ступени, отклонения, порядок — считает `app.services.metrics`. Здесь то, что
делает строку понятной человеку: имя ответственного, к чему относится строка, исходный
срок, открытый вопрос и последнее решение. Каждое — одним запросом на все строки, а не
запросом на строку: список из двухсот строк не имеет права стоить двухсот обращений к
базе (CLAUDE.md, «Read-модель на экран»).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import Row
from app.domain.clock import local_date
from app.domain.decisions import DecisionTarget
from app.domain.pult import DECISIONS, MILESTONES, PROJECTS, TASKS, AuditEntry
from app.repos.models import (
    AuditLog,
    LeaderDecision,
    LeaderQuestion,
    Milestone,
    Person,
    Project,
    Task,
)

Target = tuple[str, uuid.UUID]

# Раздел строки лестницы → вид объекта решения. Строка раздела `decisions` решается по
# объекту того решения, а не по нему самому: «поторопить» относится к работе.
SECTION_TARGET = {
    "projects": DecisionTarget.PROJECT.value,
    "milestones": DecisionTarget.MILESTONE.value,
    "tasks": DecisionTarget.TASK.value,
}

# Вид объекта решения → таблица журнала.
TARGET_TABLE = {
    DecisionTarget.PROJECT.value: PROJECTS,
    DecisionTarget.MILESTONE.value: MILESTONES,
    DecisionTarget.TASK.value: TASKS,
}


@dataclass(frozen=True, slots=True)
class RowDetail:
    context: str | None
    original_due_on: date | None
    target: Target


async def people_names(session: AsyncSession, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    wanted = set(ids)
    if not wanted:
        return {}
    rows = await session.execute(select(Person.id, Person.full_name).where(Person.id.in_(wanted)))
    # Сначала список: `dict(результат)` принимает результат за словарь — у него есть
    # `keys()` — и падает.
    return dict(rows.tuples().all())


async def _project_titles(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = await session.execute(select(Project.id, Project.title).where(Project.id.in_(ids)))
    # Сначала список: `dict(результат)` принимает результат за словарь — у него есть
    # `keys()` — и падает.
    return dict(rows.tuples().all())


async def row_details(
    session: AsyncSession, rows: Iterable[Row], zone: ZoneInfo
) -> dict[Target, RowDetail]:
    """К чему относится строка, её исходный срок и объект, по которому принимают решение."""
    by_section: dict[str, set[uuid.UUID]] = {}
    for row in rows:
        by_section.setdefault(row.section, set()).add(row.entity_id)

    found: dict[Target, RowDetail] = {}

    if ids := by_section.get("projects"):
        result = await session.execute(
            select(Project.id, Project.original_due_on).where(Project.id.in_(ids))
        )
        for project_id, original in result:
            found[("projects", project_id)] = RowDetail(
                context=None,
                original_due_on=original,
                target=(DecisionTarget.PROJECT.value, project_id),
            )

    if ids := by_section.get("milestones"):
        result = await session.execute(
            select(Milestone.id, Project.title, Milestone.original_due_on)
            .join(Project, Project.id == Milestone.project_id)
            .where(Milestone.id.in_(ids))
        )
        for milestone_id, project_title, original in result:
            found[("milestones", milestone_id)] = RowDetail(
                context=project_title,
                original_due_on=original,
                target=(DecisionTarget.MILESTONE.value, milestone_id),
            )

    if ids := by_section.get("tasks"):
        result = await session.execute(
            select(Task.id, Project.title, Task.original_due_at)
            .outerjoin(Project, Project.id == Task.project_id)
            .where(Task.id.in_(ids))
        )
        for task_id, project_title, original in result:
            found[("tasks", task_id)] = RowDetail(
                context=project_title,
                original_due_on=local_date(original, zone) if original else None,
                target=(DecisionTarget.TASK.value, task_id),
            )

    if ids := by_section.get("decisions"):
        decision_rows = await session.execute(
            select(LeaderDecision.id, LeaderDecision.target_type, LeaderDecision.target_id).where(
                LeaderDecision.id.in_(ids)
            )
        )
        decisions = list(decision_rows.tuples())
        target_titles = await titles(
            session,
            {
                (TARGET_TABLE[kind], target_id)
                for _, kind, target_id in decisions
                if kind in TARGET_TABLE
            },
        )
        for decision_id, kind, target_id in decisions:
            found[("decisions", decision_id)] = RowDetail(
                context=target_titles.get((TARGET_TABLE.get(kind, ""), target_id)),
                original_due_on=None,
                target=(kind, target_id),
            )

    return found


async def open_questions(
    session: AsyncSession, targets: Iterable[Target]
) -> dict[Target, LeaderQuestion]:
    """Самый старый открытый вопрос по каждому объекту — его видит руководитель."""
    wanted = set(targets)
    if not wanted:
        return {}
    rows = await session.scalars(
        select(LeaderQuestion)
        .where(
            LeaderQuestion.closed_at.is_(None),
            tuple_(LeaderQuestion.target_type, LeaderQuestion.target_id).in_(list(wanted)),
        )
        .order_by(LeaderQuestion.created_at)
    )
    found: dict[Target, LeaderQuestion] = {}
    for question in rows:
        found.setdefault((question.target_type, question.target_id), question)
    return found


async def last_decisions(
    session: AsyncSession, targets: Iterable[Target]
) -> dict[Target, LeaderDecision]:
    """Последнее решение руководителя по каждому объекту: чтобы не поторопить дважды."""
    wanted = set(targets)
    if not wanted:
        return {}
    rows = await session.scalars(
        select(LeaderDecision)
        .where(tuple_(LeaderDecision.target_type, LeaderDecision.target_id).in_(list(wanted)))
        .order_by(LeaderDecision.created_at.desc())
    )
    found: dict[Target, LeaderDecision] = {}
    for decision in rows:
        found.setdefault((decision.target_type, decision.target_id), decision)
    return found


async def titles(
    session: AsyncSession, entities: Iterable[tuple[str, uuid.UUID]]
) -> dict[tuple[str, uuid.UUID], str | None]:
    """Название записи по имени таблицы журнала и идентификатору.

    У решения названия нет: берётся его текст, а без текста — название объекта, по
    которому оно принято. Удалённая запись названия не получает — её в журнале видно, а
    в базе уже нет.
    """
    by_table: dict[str, set[uuid.UUID]] = {}
    for table, entity_id in entities:
        by_table.setdefault(table, set()).add(entity_id)

    found: dict[tuple[str, uuid.UUID], str | None] = {}
    for table, model in ((PROJECTS, Project), (TASKS, Task), (MILESTONES, Milestone)):
        if ids := by_table.get(table):
            result = await session.execute(select(model.id, model.title).where(model.id.in_(ids)))
            found.update({(table, entity_id): title for entity_id, title in result})

    if ids := by_table.get(DECISIONS):
        decision_rows = await session.execute(
            select(
                LeaderDecision.id,
                LeaderDecision.text,
                LeaderDecision.target_type,
                LeaderDecision.target_id,
            ).where(LeaderDecision.id.in_(ids))
        )
        decisions = list(decision_rows.tuples())
        targets = await titles(
            session,
            {
                (TARGET_TABLE[kind], target)
                for _, _, kind, target in decisions
                if kind in TARGET_TABLE
            },
        )
        for decision_id, text, kind, target in decisions:
            found[(DECISIONS, decision_id)] = text or targets.get(
                (TARGET_TABLE.get(kind, ""), target)
            )
    return found


async def audit_entries(
    session: AsyncSession,
    *,
    since: datetime,
    entity_types: Iterable[str],
    exclude_actor: uuid.UUID | None = None,
    limit: int | None = None,
) -> list[AuditEntry]:
    """Записи журнала после момента — новые первыми."""
    statement = (
        select(
            AuditLog.occurred_at,
            AuditLog.entity_type,
            AuditLog.entity_id,
            AuditLog.action,
            AuditLog.changes,
        )
        .where(AuditLog.occurred_at > since, AuditLog.entity_type.in_(list(entity_types)))
        .order_by(AuditLog.occurred_at.desc())
    )
    if exclude_actor is not None:
        statement = statement.where(
            AuditLog.actor_id.is_(None) | (AuditLog.actor_id != exclude_actor)
        )
    if limit is not None:
        statement = statement.limit(limit)
    rows = await session.execute(statement)
    return [
        AuditEntry(
            occurred_at=occurred_at,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            changes=changes or {},
        )
        for occurred_at, entity_type, entity_id, action, changes in rows
    ]


async def due_dates(
    session: AsyncSession, entities: Iterable[tuple[str, uuid.UUID]], zone: ZoneInfo
) -> dict[tuple[str, uuid.UUID], tuple[date, date | None]]:
    """Исходный и текущий срок записей: «исходный → текущий» в «Держим ли сроки?»."""
    by_table: dict[str, set[uuid.UUID]] = {}
    for table, entity_id in entities:
        by_table.setdefault(table, set()).add(entity_id)

    found: dict[tuple[str, uuid.UUID], tuple[date, date | None]] = {}
    for table, model in ((PROJECTS, Project), (MILESTONES, Milestone)):
        if ids := by_table.get(table):
            result = await session.execute(
                select(model.id, model.original_due_on, model.due_on).where(model.id.in_(ids))
            )
            found.update({(table, i): (original, due) for i, original, due in result})
    if ids := by_table.get(TASKS):
        result = await session.execute(
            select(Task.id, Task.original_due_at, Task.due_at).where(Task.id.in_(ids))
        )
        for task_id, original, due in result:
            if original is None:
                continue
            found[(TASKS, task_id)] = (
                local_date(original, zone),
                local_date(due, zone) if due else None,
            )
    return found


async def target_responsible(
    session: AsyncSession, target: Target
) -> tuple[bool, uuid.UUID | None]:
    """Есть ли объект решения и кто за него отвечает.

    Ответственный подставляется в решения «поручить», «поторопить», «эскалировать»:
    руководитель в одно касание не выбирает человека из списка — он торопит того, кто
    держит строку.
    """
    kind, target_id = target
    if kind == DecisionTarget.PROJECT.value:
        found = await session.execute(
            select(Project.id, Project.responsible_person_id).where(Project.id == target_id)
        )
    elif kind == DecisionTarget.MILESTONE.value:
        found = await session.execute(
            select(Milestone.id, Project.responsible_person_id)
            .join(Project, Project.id == Milestone.project_id)
            .where(Milestone.id == target_id)
        )
    elif kind == DecisionTarget.TASK.value:
        found = await session.execute(
            select(Task.id, Task.assignee_person_id).where(Task.id == target_id)
        )
    else:
        return False, None
    row = found.first()
    return (row is not None, row[1] if row else None)
