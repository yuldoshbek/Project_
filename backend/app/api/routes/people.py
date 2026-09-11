"""Сотрудники агентства: чтение.

**Сотрудник — не пользователь системы.** Их десятки, и в ORBITA они не входят: они
существуют, чтобы было понятно, с кого спрашивать — куратор проекта, исполнитель задачи,
участник встречи (`app.domain.people`, ADR-0011). Отдельный эндпоинт, а не поле в
справочниках: справочники отдаются одним ответом при открытии любой формы, а список
сотрудников растёт и утяжелял бы каждое такое открытие.

Заведено при ORB-020: ТЗ 6.2 требует фильтры по исполнителю и куратору, а списка людей
наружу не отдавал никто. Ведение сотрудников — отдельный экран, ORB-045.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import SessionDep
from app.api.security import get_active_user
from app.repos.models import Person

router = APIRouter(tags=["сотрудники"], dependencies=[Depends(get_active_user)])


class PersonItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    position: str | None
    department: str | None
    is_active: bool


@router.get("/people", response_model=list[PersonItem], summary="Сотрудники агентства")
async def list_people(
    session: SessionDep,
    active_only: Annotated[
        bool,
        Query(
            description=(
                "Только действующие. Для формы назначения — да; при показе старой "
                "записи — нет, иначе исчезнет исполнитель, на которого её когда-то завели"
            )
        ),
    ] = True,
    search: Annotated[str | None, Query(description="Совпадение по части ФИО")] = None,
) -> list[PersonItem]:
    statement = select(Person).order_by(Person.full_name)
    if active_only:
        statement = statement.where(Person.is_active.is_(True))
    if search:
        statement = statement.where(Person.full_name.ilike(f"%{search.strip()}%"))

    return [PersonItem.model_validate(row) for row in await session.scalars(statement)]
