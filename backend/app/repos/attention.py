"""Снимок данных для лестницы внимания — read-модель Пульта.

Здесь только чтение и перевод строк базы в `app.domain.attention.Item`. Правило ступеней
живёт в домене, расчёт вызывает `app.services.metrics`: так «что если» считает по тому же
снимку тем же кодом и не может ничего записать.

Число запросов не зависит от числа записей — по одному на вид записи и на каждый признак.
Запрос на проект превратил бы открытие Пульта в двести обращений к базе, и заметили бы это
не сразу, а когда проектов станет много.

**Даты — по Ташкенту.** Сроки задач, признак жизни и дата вопроса хранятся моментами в UTC
(инвариант 8), а лестница сравнивает календарные дни. Перевод идёт через
`app.domain.clock.local_date`: у момента из базы пояс UTC, и дата, взятая напрямую,
делает работу просроченной на сутки раньше.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import Item
from app.domain.clock import local_date
from app.domain.decisions import DecisionState, DecisionTarget
from app.domain.dictionaries import OrganizationRole, ProjectStatus, TaskStatus
from app.repos.models import (
    LeaderDecision,
    LeaderQuestion,
    Milestone,
    Organization,
    Project,
    ProjectOrganization,
    Task,
)

PROJECT_TERMINAL = [status.value for status in ProjectStatus if status.is_terminal]
TASK_TERMINAL = [status.value for status in TaskStatus if status.is_terminal]

Key = tuple[str, uuid.UUID]


async def load_items(session: AsyncSession, *, zone: ZoneInfo) -> list[Item]:
    """Все незавершённые записи, из которых складывается лестница.

    Ижро сюда придёт в блоке 2 вместе с признаком жизни поручения: контрольная отметка,
    движение связанной задачи, промежуточная информация (ТЗ 4).
    """
    awaiting = await _open_questions(session, zone)
    items: list[Item] = []
    items += await _projects(session, zone, awaiting)
    items += await _milestones(session, awaiting)
    items += await _tasks(session, zone, awaiting)
    items += await _decisions(session, zone)
    return items


async def _open_questions(session: AsyncSession, zone: ZoneInfo) -> dict[Key, date]:
    """Открытые вопросы к руководителю: объект → дата самого старого из них.

    Самый старый, а не последний: «старейшее ожидание» — это ответ Пульта на вопрос «что
    ждёт моего решения» (ТЗ 5), и новый вопрос по тому же объекту не обнуляет срок, который
    руководитель уже заставил ждать.
    """
    rows = await session.execute(
        select(
            LeaderQuestion.target_type,
            LeaderQuestion.target_id,
            func.min(LeaderQuestion.created_at),
        )
        .where(LeaderQuestion.closed_at.is_(None))
        .group_by(LeaderQuestion.target_type, LeaderQuestion.target_id)
    )
    return {
        (target_type, target_id): local_date(asked_at, zone)
        for target_type, target_id, asked_at in rows
    }


def _outside_lead_projects() -> Select[tuple[uuid.UUID]]:
    """Проекты, у которых головное ведомство — не агентство и не Центр.

    Первая половина правила «зависит от чужих» (ТЗ 4); вторая — нет движения — живёт в
    домене вместе с порогом молчания.
    """
    return (
        select(ProjectOrganization.project_id)
        .join(Organization, Organization.id == ProjectOrganization.organization_id)
        .where(
            ProjectOrganization.role == OrganizationRole.LEAD_AGENCY.value,
            Organization.is_founded_by_agency.is_(False),
        )
    )


async def _latest_by_project(
    session: AsyncSession, model: type[Task] | type[Milestone]
) -> dict[uuid.UUID, datetime]:
    """Самое свежее движение по задачам или вехам каждого проекта одним запросом.

    Созданная и ни разу не правленная запись — тоже движение: `updated_at` у неё пуст, и
    без `created_at` она выглядела бы так, будто по проекту ничего не происходило.
    """
    moment = func.max(func.coalesce(model.updated_at, model.created_at))
    rows = await session.execute(
        select(model.project_id, moment)
        .where(model.project_id.is_not(None))
        .group_by(model.project_id)
    )
    return {project_id: seen for project_id, seen in rows if seen is not None}


async def _projects(session: AsyncSession, zone: ZoneInfo, awaiting: dict[Key, date]) -> list[Item]:
    outside = set(await session.scalars(_outside_lead_projects()))
    by_task = await _latest_by_project(session, Task)
    by_milestone = await _latest_by_project(session, Milestone)

    rows = await session.execute(
        select(
            Project.id,
            Project.title,
            Project.due_on,
            Project.responsible_person_id,
            Project.created_at,
            Project.updated_at,
            Project.impediment_updated_at,
        ).where(Project.status_code.notin_(PROJECT_TERMINAL))
    )

    items: list[Item] = []
    for project_id, title, due_on, responsible, created, updated, impediment in rows:
        # Признак жизни проекта — самое свежее из: правки самого проекта (включая строку
        # «что мешает»), движения задач и вех. Без собственных правок новый проект без
        # задач «молчал» бы с первого дня.
        moments = [
            created,
            updated,
            impediment,
            by_task.get(project_id),
            by_milestone.get(project_id),
        ]
        life = max(local_date(moment, zone) for moment in moments if moment is not None)
        items.append(
            Item(
                section="projects",
                entity_id=project_id,
                title=title,
                due_on=due_on,
                last_sign_of_life=life,
                awaiting_since=awaiting.get((DecisionTarget.PROJECT.value, project_id)),
                lead_is_outside=project_id in outside,
                responsible_person_id=responsible,
            )
        )
    return items


async def _milestones(session: AsyncSession, awaiting: dict[Key, date]) -> list[Item]:
    rows = await session.execute(
        select(Milestone.id, Milestone.title, Milestone.due_on, Project.responsible_person_id)
        .join(Project, Project.id == Milestone.project_id)
        .where(
            Milestone.is_passed.is_(False),
            Project.status_code.notin_(PROJECT_TERMINAL),
        )
    )
    return [
        Item(
            section="milestones",
            entity_id=milestone_id,
            title=title,
            due_on=due_on,
            # Своего движения у вехи нет — её молчание считается у проекта.
            last_sign_of_life=None,
            awaiting_since=awaiting.get((DecisionTarget.MILESTONE.value, milestone_id)),
            lead_is_outside=False,
            # Ответственный за веху — ответственный проекта: у вехи своего нет (ТЗ 3.1).
            responsible_person_id=responsible,
        )
        for milestone_id, title, due_on, responsible in rows
    ]


async def _tasks(session: AsyncSession, zone: ZoneInfo, awaiting: dict[Key, date]) -> list[Item]:
    rows = await session.execute(
        select(
            Task.id,
            Task.title,
            Task.due_at,
            Task.assignee_person_id,
            func.coalesce(Task.updated_at, Task.created_at),
        )
        .outerjoin(Project, Project.id == Task.project_id)
        .where(
            Task.status.notin_(TASK_TERMINAL),
            # Задачи завершённого или отменённого проекта в лестницу не попадают, как и
            # его вехи: работа закончена, и спрашивать с неё больше нечего.
            or_(Task.project_id.is_(None), Project.status_code.notin_(PROJECT_TERMINAL)),
        )
    )
    return [
        Item(
            section="tasks",
            entity_id=task_id,
            title=title,
            # Срок задачи — момент, а сравнение с «сегодня» идёт по календарным дням
            # Ташкента (инвариант 8).
            due_on=local_date(due_at, zone) if due_at is not None else None,
            last_sign_of_life=local_date(moved, zone),
            awaiting_since=awaiting.get((DecisionTarget.TASK.value, task_id)),
            lead_is_outside=False,
            responsible_person_id=assignee,
        )
        for task_id, title, due_at, assignee, moved in rows
    ]


async def _decisions(session: AsyncSession, zone: ZoneInfo) -> list[Item]:
    """Решения руководителя, которые он принял, а исполнения нет.

    Они стоят в лестнице наравне с работой: решение, о котором забыли, — это ровно то,
    из-за чего система и заводилась. На ступень «ждёт решения» они не попадают никогда:
    решение уже принято, ждут его исполнения.
    """
    rows = await session.execute(
        select(
            LeaderDecision.id,
            LeaderDecision.text,
            LeaderDecision.kind,
            LeaderDecision.due_on,
            LeaderDecision.assignee_person_id,
            func.coalesce(LeaderDecision.updated_at, LeaderDecision.created_at),
        ).where(LeaderDecision.state == DecisionState.OPEN.value)
    )
    return [
        Item(
            section="decisions",
            entity_id=decision_id,
            title=text,
            kind=kind,
            due_on=due_on,
            last_sign_of_life=local_date(moved, zone),
            awaiting_since=None,
            lead_is_outside=False,
            responsible_person_id=assignee,
        )
        for decision_id, text, kind, due_on, assignee, moved in rows
    ]
