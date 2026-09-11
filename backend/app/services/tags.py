"""Теги задач: сценарии использования.

Весь модуль держится на одном правиле: **ввод существующего тега не создаёт второй**
(критерий ORB-015). Нарушить его легко и незаметно — достаточно вставлять тег по строке
как есть. Через месяц в словаре будут «ДЗЗ», «дзз» и «ДЗЗ », запрос «покажи всё по ДЗЗ»
вернёт треть, и доверие к тегам кончится раньше, чем кто-то поймёт причину.

Уникальность обеспечивает `citext`-столбец, а не проверка здесь: проверку обходит первый
же импорт данных, тип столбца — никто. Код отвечает за другое — за то, чтобы **найти**
существующий тег до вставки и вернуть его написание, а не переписать чужое своим.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.checklists import normalize_tag
from app.domain.errors import RuleViolationError
from app.repos.models import Tag, TaskTag
from app.services.tasks import get as get_task


async def list_all(session: AsyncSession) -> list[Tag]:
    """Словарь тегов по алфавиту — то, из чего выбирают при вводе."""
    return list(await session.scalars(select(Tag).order_by(Tag.name)))


async def ensure(session: AsyncSession, name: str) -> Tag:
    """Тег с таким именем: найденный или заведённый.

    Сначала поиск, потом вставка. Сравнение регистронезависимое — его делает тип
    столбца, поэтому здесь обычное равенство, а не `lower()` с обеих сторон: `lower()`
    по `citext` ещё и отключил бы индекс.

    Найденный тег возвращается **со своим написанием**. Человек, набравший «дзз» вслед за
    заведённым «ДЗЗ», получит «ДЗЗ» — и это не своеволие: переписать написание значило бы
    менять его у всех задач, которые уже помечены, из-за одного ввода в одной карточке.
    """
    cleaned = _valid(name)

    found = await session.scalar(select(Tag).where(Tag.name == cleaned))
    if found is not None:
        return found

    tag = Tag(name=cleaned)
    session.add(tag)
    await session.flush()
    return tag


async def list_for_task(session: AsyncSession, task_id: uuid.UUID) -> list[Tag]:
    await get_task(session, task_id)
    return list(
        await session.scalars(
            select(Tag)
            .join(TaskTag, TaskTag.tag_id == Tag.id)
            .where(TaskTag.task_id == task_id)
            .order_by(Tag.name)
        )
    )


async def set_for_task(
    session: AsyncSession, task_id: uuid.UUID, names: Sequence[str]
) -> list[Tag]:
    """Теги задачи набором целиком, а не по одному.

    Приходит весь набор — как и порядок чек-листа, и по той же причине: «добавь этот,
    убери тот» двумя запросами оставляет задачу в состоянии, которого пользователь не
    выбирал, если второй запрос не дошёл.

    Повторы внутри набора схлопываются: «ДЗЗ, дзз» — это один тег, названный дважды, а не
    ошибка ввода, о которой надо сообщать.
    """
    await get_task(session, task_id)

    wanted: dict[str, Tag] = {}
    for name in names:
        tag = await ensure(session, name)
        wanted[str(tag.name).casefold()] = tag

    current = {
        link.tag_id: link
        for link in await session.scalars(select(TaskTag).where(TaskTag.task_id == task_id))
    }
    keep = {tag.id for tag in wanted.values()}

    for tag_id, link in current.items():
        if tag_id not in keep:
            await session.delete(link)

    for tag in wanted.values():
        if tag.id not in current:
            session.add(TaskTag(task_id=task_id, tag_id=tag.id))

    await session.flush()
    return sorted(wanted.values(), key=lambda tag: str(tag.name).casefold())


def _valid(name: str) -> str:
    try:
        return normalize_tag(name)
    except ValueError as error:
        raise RuleViolationError("Тег не годится", detail=str(error)) from error
