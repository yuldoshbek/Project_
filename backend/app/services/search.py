"""Поиск по всем разделам (ТЗ 6, допущение V19): находки по видам, в порядке вида.

Сценарий тонкий намеренно: правило строки — в `app.domain.search`, запрос — в
`app.repos.search`. Здесь только то, что делает ответ экраном: группы по виду, не больше
`PER_KIND` находок в группе и признак «есть ещё».
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.search import PER_KIND, HitKind, normalize, spellings
from app.repos import search as read_model
from app.repos.search import Hit


@dataclass(frozen=True, slots=True)
class Group:
    kind: HitKind
    hits: list[Hit]
    more: bool


@dataclass(frozen=True, slots=True)
class SearchView:
    query: str
    groups: list[Group]


async def search(session: AsyncSession, query: str) -> SearchView:
    """Находки по запросу. Слишком короткий запрос не ищется — ответ пустой, а не ошибка:
    экран зовёт поиск на каждый набранный знак, и первая буква — не повод для отказа."""
    texts = spellings(query)
    if not texts:
        return SearchView(query=normalize(query), groups=[])
    hits = await read_model.search(session, texts, per_kind=PER_KIND)
    groups: list[Group] = []
    for kind in HitKind:
        found = [hit for hit in hits if hit.kind is kind]
        if found:
            groups.append(Group(kind=kind, hits=found[:PER_KIND], more=len(found) > PER_KIND))
    return SearchView(query=normalize(query), groups=groups)
