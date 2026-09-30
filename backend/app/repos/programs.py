"""Read-модель раздела «Программы»: какие записи в него входят и темп закрытия задач.

Сами программы и подпроекты читает read-модель «Проектов» (`app.repos.projects.projects`)
по списку отсюда: программа — тот же проект, и второе чтение тех же полей разошлось бы с
первым на первой же правке. Здесь — только то, чего у «Проектов» нет.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from datetime import datetime

from sqlalchemy import func, select, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.dictionaries import TaskStatus
from app.repos.models import Project, Task


async def scope(session: AsyncSession) -> list[uuid.UUID]:
    """Программы и их подпроекты — одним запросом.

    Подпроект бывает только у программы (`app.domain.projects.validate_program`), но берём
    его по признаку родителя, а не по наличию родителя вообще: правило держит сервис, а
    раздел не должен молча показать чужое, если оно однажды нарушится.
    """
    parent = aliased(Project)
    programs = select(Project.id).where(Project.is_multiyear.is_(True))
    children = (
        select(Project.id)
        .join(parent, parent.id == Project.parent_project_id)
        .where(parent.is_multiyear.is_(True))
    )
    return list(await session.scalars(union(programs, children)))


async def closed_tasks_between(
    session: AsyncSession, project_ids: Collection[uuid.UUID], since: datetime, until: datetime
) -> dict[uuid.UUID, int]:
    """Сколько задач каждого проекта закрыто в окне `[since, until)` — темп «успеваем?».

    Только готовые: отменённая задача — не темп работы, а отказ от неё. Окно считает
    сервис показателей (`metrics.pace_window`).
    """
    if not project_ids:
        return {}
    statement = (
        select(Task.project_id, func.count())
        .where(
            Task.project_id.in_(list(project_ids)),
            Task.status == TaskStatus.DONE.value,
            Task.completed_at >= since,
            Task.completed_at < until,
        )
        .group_by(Task.project_id)
    )
    return {
        project_id: count
        for project_id, count in await session.execute(statement)
        if project_id is not None
    }
