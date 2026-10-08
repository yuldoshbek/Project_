"""Read-модель раздела «Идеи и карты»: идеи со ссылками на выросшее, карты, узлы карты.

Раздел собирается тремя запросами — идеи, карты со счётом узлов, узлы открытой карты, — у
каждого связанные проект и задача приходят соединением, а не обходом по записям.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.repos.models import Idea, IdeaMap, MapNode, Project, Task, User


@dataclass(frozen=True, slots=True)
class Link:
    """Настоящая запись, с которой связана идея или узел: проект или задача."""

    type: str
    id: uuid.UUID
    code: str
    title: str


@dataclass(frozen=True, slots=True)
class IdeaRow:
    id: uuid.UUID
    text: str
    author: str
    step: str
    outcome: str | None
    created_at: datetime
    review_at: datetime | None
    decided_at: datetime | None
    link: Link | None
    version: int


@dataclass(frozen=True, slots=True)
class MapRow:
    id: uuid.UUID
    title: str
    mode: str
    nodes: int
    linked: int
    changed_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class NodeRow:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    text: str
    x: int
    y: int
    link: Link | None
    version: int


def _link(
    project: tuple[uuid.UUID | None, str | None, str | None],
    task: tuple[uuid.UUID | None, str | None, str | None],
) -> Link | None:
    project_id, project_code, project_title = project
    if project_id is not None and project_code is not None and project_title is not None:
        return Link(type="project", id=project_id, code=project_code, title=project_title)
    task_id, task_code, task_title = task
    if task_id is not None and task_code is not None and task_title is not None:
        return Link(type="task", id=task_id, code=task_code, title=task_title)
    return None


async def ideas(session: AsyncSession, ids: list[uuid.UUID] | None = None) -> list[IdeaRow]:
    """Все идеи, новые первыми; порядок вопросов задаёт сервис показателей."""
    statement = (
        select(
            Idea.id,
            Idea.text,
            User.role,
            Idea.step,
            Idea.outcome,
            Idea.created_at,
            Idea.review_at,
            Idea.decided_at,
            Project.id,
            Project.code,
            Project.title,
            Task.id,
            Task.code,
            Task.title,
            Idea.version,
        )
        .join(User, User.id == Idea.author_id)
        .outerjoin(Project, Project.id == Idea.project_id)
        .outerjoin(Task, Task.id == Idea.task_id)
        .order_by(Idea.created_at.desc(), Idea.id)
    )
    if ids is not None:
        statement = statement.where(Idea.id.in_(ids))
    rows = await session.execute(statement)
    return [
        IdeaRow(
            id=row[0],
            text=row[1],
            author=row[2],
            step=row[3],
            outcome=row[4],
            created_at=row[5],
            review_at=row[6],
            decided_at=row[7],
            link=_link((row[8], row[9], row[10]), (row[11], row[12], row[13])),
            version=row[14],
        )
        for row in rows
    ]


async def maps(session: AsyncSession) -> list[MapRow]:
    """Карты, последние правленые первыми; правка узла — тоже правка карты."""
    node = aliased(MapNode)
    counts = (
        select(
            node.map_id.label("map_id"),
            func.count().label("nodes"),
            func.count(node.project_id).label("projects"),
            func.count(node.task_id).label("tasks"),
            func.max(func.coalesce(node.updated_at, node.created_at)).label("changed"),
        )
        .group_by(node.map_id)
        .subquery()
    )
    changed = func.greatest(
        func.coalesce(IdeaMap.updated_at, IdeaMap.created_at),
        func.coalesce(counts.c.changed, IdeaMap.created_at),
    )
    rows = await session.execute(
        select(
            IdeaMap.id,
            IdeaMap.title,
            IdeaMap.mode,
            func.coalesce(counts.c.nodes, 0),
            func.coalesce(counts.c.projects, 0) + func.coalesce(counts.c.tasks, 0),
            changed,
            IdeaMap.version,
        )
        .outerjoin(counts, counts.c.map_id == IdeaMap.id)
        .order_by(changed.desc(), IdeaMap.id)
    )
    return [
        MapRow(
            id=map_id,
            title=title,
            mode=mode,
            nodes=nodes,
            linked=linked,
            changed_at=changed_at,
            version=version,
        )
        for map_id, title, mode, nodes, linked, changed_at, version in rows
    ]


async def map_row(session: AsyncSession, map_id: uuid.UUID) -> MapRow | None:
    found = [row for row in await maps(session) if row.id == map_id]
    return found[0] if found else None


async def nodes(session: AsyncSession, map_id: uuid.UUID) -> list[NodeRow]:
    """Узлы карты по порядку заведения: контур телефона идёт в том же порядке, что и полотно."""
    rows = await session.execute(
        select(
            MapNode.id,
            MapNode.parent_id,
            MapNode.text,
            MapNode.x,
            MapNode.y,
            Project.id,
            Project.code,
            Project.title,
            Task.id,
            Task.code,
            Task.title,
            MapNode.version,
        )
        .outerjoin(Project, Project.id == MapNode.project_id)
        .outerjoin(Task, Task.id == MapNode.task_id)
        .where(MapNode.map_id == map_id)
        .order_by(MapNode.created_at, MapNode.id)
    )
    return [
        NodeRow(
            id=row[0],
            parent_id=row[1],
            text=row[2],
            x=row[3],
            y=row[4],
            link=_link((row[5], row[6], row[7]), (row[8], row[9], row[10])),
            version=row[11],
        )
        for row in rows
    ]


async def parents(session: AsyncSession, map_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID | None]:
    """Узел → родитель по всей карте — для проверки кольца и удаления ветки."""
    rows = await session.execute(
        select(MapNode.id, MapNode.parent_id).where(MapNode.map_id == map_id)
    )
    return dict(rows.tuples().all())
