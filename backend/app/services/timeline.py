"""Ход событий по записи: реплики и изменения одним потоком.

Два списка рядом — «комментарии» и «история изменений» — читатель сводит в голове, и
сводит неверно: он видит, что срок перенесли, и не видит, что двумя минутами раньше об
этом договорились в реплике. Смысл ровно в порядке — кто на что отвечал и что за чем
последовало, — а порядок виден только тогда, когда оба вида событий стоят в одной колонке.

Источников два и объединять их в SQL нечем: у реплик своя таблица, у изменений своя, поля
разные. Слияние идёт в памяти — и это осознанно: события одной записи исчисляются
десятками, а не тысячами, а попытка сшить их запросом дала бы `UNION` из разнородных
столбцов, который нельзя ни прочитать, ни расширить третьим источником (вложения, ORB-017).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.comments import CommentTarget
from app.domain.errors import NotFoundError
from app.repos.models import AuditLog, Comment, Project, Task, User
from app.services.comments import CommentView, list_for, target_exists


class EventKind(StrEnum):
    COMMENT = "comment"
    CHANGE = "change"


# Журнал изменений хранит `entity_type` именем таблицы — «projects», — а комментарии
# говорят о том же во множественном числе иначе: «project». Совпадения нет, и без явного
# перевода лента изменений оказалась бы пустой, ничем себя не выдав: запрос отрабатывает,
# просто ничего не находит.
AUDIT_TABLE = {
    CommentTarget.PROJECT: Project.__tablename__,
    CommentTarget.TASK: Task.__tablename__,
}
COMMENT_TABLE = Comment.__tablename__

CREATED = "created"
"""Действие журнала, которое у реплик в ленту не идёт: оно и есть сама реплика."""


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    """Одно событие ленты — реплика или изменение."""

    kind: EventKind
    at: datetime
    actor_id: uuid.UUID | None
    actor_name: str | None

    comment: CommentView | None = None

    action: str | None = None
    changes: dict[str, Any] | None = None
    # К чему относится изменение: к самой записи или к реплике под ней. Без этого поля
    # «[updated] body» неотличимо — правили текст задачи или текст комментария, — и лента
    # на экране подписывает событие наугад.
    subject: str | None = None


async def of(
    session: AsyncSession, entity_type: CommentTarget, entity_id: uuid.UUID
) -> list[TimelineEvent]:
    """События одной записи в порядке, в котором они происходили.

    Порядок по возрастанию: ленту читают сверху вниз как разговор, а не как список
    новостей. При совпадении времени до микросекунды реплика идёт после изменения —
    обсуждают обычно то, что уже случилось.
    """
    if not await target_exists(session, entity_type, entity_id):
        raise NotFoundError("Запись не найдена")

    events: list[TimelineEvent] = []
    names = await _actor_names(session)

    for view in await list_for(session, entity_type, entity_id):
        events.append(
            TimelineEvent(
                kind=EventKind.COMMENT,
                at=view.comment.created_at,
                actor_id=view.comment.author_id,
                actor_name=names.get(view.comment.author_id),
                comment=view,
            )
        )

    for entry in await _changes(session, entity_type, entity_id):
        events.append(
            TimelineEvent(
                kind=EventKind.CHANGE,
                at=entry.occurred_at,
                actor_id=entry.actor_id,
                actor_name=names.get(entry.actor_id),
                action=entry.action,
                changes=entry.changes,
                subject=entry.entity_type,
            )
        )

    events.sort(key=lambda event: (event.at, event.kind is EventKind.COMMENT))
    return events


async def _changes(
    session: AsyncSession, entity_type: CommentTarget, entity_id: uuid.UUID
) -> list[AuditLog]:
    """Изменения самой записи и правки реплик под ней.

    **Появление реплики из журнала не берётся.** Оно уже есть в ленте — самой репликой, —
    и вторая строка «[created] body, author_id, entity_id, entity_type» рядом с текстом
    удлиняет поток вдвое, не добавляя ничего: перечень имён полей читателю не говорит
    ничего такого, чего не сказал сам текст. Найдено на живом стенде: проверки проходили,
    а лента читалась вдвое хуже.

    Правка и удаление реплики берутся: «написал» и «поправил написанное» — разные
    события, и второе без первого не читается.
    """
    comment_ids = list(
        await session.scalars(
            select(Comment.id).where(
                Comment.entity_type == entity_type.value, Comment.entity_id == entity_id
            )
        )
    )

    own = (AuditLog.entity_type == AUDIT_TABLE[entity_type]) & (AuditLog.entity_id == entity_id)
    condition = own
    if comment_ids:
        condition = own | (
            (AuditLog.entity_type == COMMENT_TABLE)
            & (AuditLog.entity_id.in_(comment_ids))
            & (AuditLog.action != CREATED)
        )

    return list(
        await session.scalars(select(AuditLog).where(condition).order_by(AuditLog.occurred_at))
    )


async def _actor_names(session: AsyncSession) -> dict[uuid.UUID | None, str]:
    """Имена пользователей разом: их двое, и запрос на событие был бы расточительством."""
    return {user.id: user.full_name for user in await session.scalars(select(User))}
