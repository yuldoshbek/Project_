"""Read-модель Захвата: недавние записи одним запросом.

Роль автора и задача приходят соединением, а не обращением на каждую строку (CLAUDE.md,
«Read-модель на экран»).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import Capture, Task, User


@dataclass(frozen=True, slots=True)
class CaptureRow:
    id: uuid.UUID
    kind: str
    text: str
    due_on: date | None
    author_role: str
    created_at: datetime
    task_id: uuid.UUID | None
    task_code: str | None
    task_title: str | None
    task_due_at: datetime | None


async def recent(
    session: AsyncSession, *, limit: int, ids: list[uuid.UUID] | None = None
) -> list[CaptureRow]:
    """Последние записи обоих — сначала новые. `ids` — только эти (ответ на запись)."""
    statement = (
        select(Capture, User.role, Task.code, Task.title, Task.due_at)
        .join(User, User.id == Capture.author_id)
        .outerjoin(Task, Task.id == Capture.task_id)
        # Время — начало транзакции (`now()`), и у записей одной транзакции оно одно.
        # Второй ключ — ради одинакового порядка от запроса к запросу, а не хронологии.
        .order_by(Capture.created_at.desc(), Capture.id)
        .limit(limit)
    )
    if ids is not None:
        statement = statement.where(Capture.id.in_(ids))
    rows = await session.execute(statement)
    return [
        CaptureRow(
            id=capture.id,
            kind=capture.kind,
            text=capture.text,
            due_on=capture.due_on,
            author_role=role,
            created_at=capture.created_at,
            task_id=capture.task_id,
            task_code=code,
            task_title=title,
            task_due_at=due_at,
        )
        for capture, role, code, title, due_at in rows
    ]
