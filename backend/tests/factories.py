"""Записи для тестов: проект, задача, веха — с минимумом обязательных полей.

Одно место, чтобы тесты Пульта и показателей заводили данные одинаково: две копии
фабрики расходятся при первом новом обязательном поле, и падает только одна из них.
"""

from __future__ import annotations

import itertools
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dictionaries import ProjectStatus, TaskStatus
from app.repos.models import Milestone, Person, Project, ProjectTypeRef, Task

_numbers = itertools.count(1)


async def make_person(session: AsyncSession, name: str = "Сотрудник Т.") -> Person:
    person = Person(full_name=name)
    session.add(person)
    await session.flush()
    return person


async def make_project(
    session: AsyncSession,
    *,
    due_on: date,
    status: ProjectStatus = ProjectStatus.IN_PROGRESS,
    responsible: Person | None = None,
    title: str | None = None,
) -> Project:
    project_type = await session.scalar(select(ProjectTypeRef.id).limit(1))
    assert project_type is not None
    number = next(_numbers)
    project = Project(
        code=f"PRJ-T-{number:04d}",
        title=title or f"Проект {number}",
        project_type_id=project_type,
        started_on=due_on - timedelta(days=90),
        due_on=due_on,
        original_due_on=due_on,
        status_code=status.value,
        status_reason="причина для проверки" if status.requires_reason else None,
        responsible_person_id=responsible.id if responsible else None,
    )
    session.add(project)
    await session.flush()
    return project


async def make_task(
    session: AsyncSession,
    *,
    due_at: datetime | None,
    project: Project | None = None,
    assignee: Person | None = None,
    title: str | None = None,
) -> Task:
    number = next(_numbers)
    task = Task(
        code=f"TSK-T-{number:04d}",
        title=title or f"Задача {number}",
        project_id=project.id if project else None,
        assignee_person_id=assignee.id if assignee else None,
        status=TaskStatus.IN_PROGRESS.value,
        due_at=due_at,
        original_due_at=due_at,
    )
    session.add(task)
    await session.flush()
    return task


async def make_milestone(
    session: AsyncSession, *, project: Project, due_on: date, title: str | None = None
) -> Milestone:
    number = next(_numbers)
    milestone = Milestone(
        project_id=project.id,
        title=title or f"Веха {number}",
        due_on=due_on,
        original_due_on=due_on,
        sort_order=number,
    )
    session.add(milestone)
    await session.flush()
    return milestone
