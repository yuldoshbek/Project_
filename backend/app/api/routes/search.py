"""Поиск по всем разделам — один запрос на набранную строку (ТЗ 6, V19).

Ответ — договор панели поиска `frontend/src/sections/search/model.ts`: находки по видам,
по виду экран открывает карточку своего раздела.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel

from app.api.deps import SessionDep
from app.api.transaction import transactional_router
from app.domain.search import MAX_LENGTH
from app.services import search as service

router = transactional_router(tags=["поиск"])


class SearchHit(BaseModel):
    id: uuid.UUID
    title: str
    code: str | None
    context: str | None


class SearchGroup(BaseModel):
    kind: str
    hits: list[SearchHit]
    more: bool


class SearchResponse(BaseModel):
    query: str
    groups: list[SearchGroup]


@router.get("/search", response_model=SearchResponse, summary="Поиск по всем разделам")
async def search(
    session: SessionDep,
    q: Annotated[str, Query(max_length=MAX_LENGTH * 2)] = "",
) -> SearchResponse:
    view = await service.search(session, q)
    return SearchResponse(
        query=view.query,
        groups=[
            SearchGroup(
                kind=group.kind.value,
                hits=[
                    SearchHit(id=hit.id, title=hit.title, code=hit.code, context=hit.context)
                    for hit in group.hits
                ],
                more=group.more,
            )
            for group in view.groups
        ],
    )
