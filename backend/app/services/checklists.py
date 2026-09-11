"""Чек-листы задач: сценарии использования.

Прогресс здесь считается, а не хранится (`app.domain.checklists`). Главное место в
модуле — не создание пункта, а `progress_for`: список задач должен показывать прогресс
каждой, и сделать это отдельным запросом на задачу означало бы сто запросов на экран из
ста строк. Один запрос с группировкой.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Integer, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.checklists import ChecklistProgress, progress
from app.domain.errors import NotFoundError, RuleViolationError
from app.repos.models import TaskChecklistItem
from app.services.tasks import get as get_task

_UNSET: Any = object()

EMPTY = progress(done=0, total=0)
"""Прогресс задачи без чек-листа. Не ноль процентов, а отсутствие ответа."""


@dataclass(slots=True)
class ChecklistItemDraft:
    text: str


@dataclass(slots=True)
class ChecklistItemPatch:
    text: Any = _UNSET
    is_done: Any = _UNSET

    def assigned(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__slots__
            if getattr(self, name) is not _UNSET
        }


async def list_for_task(session: AsyncSession, task_id: uuid.UUID) -> list[TaskChecklistItem]:
    """Пункты в заданном человеком порядке.

    Задача проверяется на существование: чек-лист несуществующей задачи — это `404`, а не
    пустой список. Пустой список означал бы «пунктов нет», и опечатка в адресе выглядела
    бы как только что вычищенный кем-то чек-лист.
    """
    await get_task(session, task_id)

    rows = await session.scalars(
        select(TaskChecklistItem)
        .where(TaskChecklistItem.task_id == task_id)
        .order_by(TaskChecklistItem.sort_order, TaskChecklistItem.created_at)
    )
    return list(rows)


async def get(session: AsyncSession, item_id: uuid.UUID) -> TaskChecklistItem:
    item = await session.get(TaskChecklistItem, item_id)
    if item is None:
        raise NotFoundError("Пункт чек-листа не найден")
    return item


async def create(
    session: AsyncSession, task_id: uuid.UUID, draft: ChecklistItemDraft
) -> TaskChecklistItem:
    await get_task(session, task_id)

    last = await session.scalar(
        select(func.max(TaskChecklistItem.sort_order)).where(TaskChecklistItem.task_id == task_id)
    )
    item = TaskChecklistItem(
        task_id=task_id,
        text=draft.text.strip(),
        is_done=False,
        sort_order=(last or 0) + 1,
    )
    session.add(item)
    await session.flush()
    return item


async def update(
    session: AsyncSession, item_id: uuid.UUID, patch: ChecklistItemPatch
) -> TaskChecklistItem:
    item = await get(session, item_id)
    for name, value in patch.assigned().items():
        setattr(item, name, value.strip() if name == "text" else value)
    await session.flush()
    return item


async def delete(session: AsyncSession, item_id: uuid.UUID) -> None:
    item = await get(session, item_id)
    await session.delete(item)
    await session.flush()


async def reorder(
    session: AsyncSession, task_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> list[TaskChecklistItem]:
    """Переупорядочивание списком целиком, а не сдвигом по одной.

    Приходит весь порядок: частичная перестановка «подними этот пункт на один вверх»
    оставляет список в неопределённом состоянии, если два запроса пришли подряд.

    Присланный список обязан совпадать с имеющимся по составу — иначе перетаскивание,
    начатое до того, как пункт удалили, тихо оставило бы часть пунктов с прежним
    порядком, и после перезагрузки чек-лист выглядел бы иначе, чем только что на экране.
    Та же проверка и по той же причине, что у вех (ORB-012).
    """
    existing = {
        item.id: item
        for item in await session.scalars(
            select(TaskChecklistItem).where(TaskChecklistItem.task_id == task_id)
        )
    }
    if len(ordered_ids) != len(existing) or set(ordered_ids) != set(existing):
        raise RuleViolationError(
            "Присланный порядок не совпадает с составом чек-листа",
            detail="список изменился: обновите карточку и повторите",
        )

    for position, item_id in enumerate(ordered_ids, start=1):
        existing[item_id].sort_order = position

    await session.flush()
    return [existing[item_id] for item_id in ordered_ids]


async def progress_for(
    session: AsyncSession, task_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, ChecklistProgress]:
    """Прогресс чек-листа сразу для набора задач.

    **Один запрос на весь список, а не по запросу на задачу.** Прогресс нужен в списке
    задач (критерий ORB-015), а список — это сотни строк: запрос на строку превращает
    открытие экрана в сотню обращений к базе, и замечают это не сразу, а когда задач
    станет много.

    Задачи без пунктов в ответе отсутствуют: у них прогресса нет, и подставлять им ноль
    здесь значило бы решать за вызывающего. Он берёт `EMPTY` и знает, что это значит.
    """
    if not task_ids:
        return {}

    done = func.sum(case((TaskChecklistItem.is_done, 1), else_=0)).cast(Integer)
    rows = await session.execute(
        select(TaskChecklistItem.task_id, done, func.count())
        .where(TaskChecklistItem.task_id.in_(task_ids))
        .group_by(TaskChecklistItem.task_id)
    )
    return {
        task_id: progress(done=int(done_count or 0), total=int(total))
        for task_id, done_count, total in rows
    }


async def progress_of(session: AsyncSession, task_id: uuid.UUID) -> ChecklistProgress:
    """Прогресс одной задачи. Тонкая обёртка: правило считается в одном месте."""
    found = await progress_for(session, [task_id])
    return found.get(task_id, EMPTY)
