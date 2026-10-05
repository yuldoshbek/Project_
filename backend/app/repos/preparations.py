"""Read-модель раздела «Доклады и мероприятия».

Раздел собирается фиксированным числом запросов — подготовки, пункты, запросы сведений —
а не обходом по записи (CLAUDE.md, «Read-модель на экран»). Отсюда же строки лестницы
Пульта (`app.repos.attention`): перевод подготовки в `Item` — одна функция на оба экрана.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Subquery, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import Item
from app.domain.clock import local_date
from app.domain.preparations import PrepStage, SourceKind
from app.repos.models import (
    InfoRequest,
    Organization,
    Person,
    Preparation,
    PreparationItem,
    Project,
)

SECTION = "preparations"
"""Раздел строки лестницы — как у экрана Пульта (`RowSection`)."""


@dataclass(frozen=True, slots=True)
class RequestRecord:
    id: uuid.UUID
    preparation_id: uuid.UUID
    what: str
    source_kind: SourceKind
    source_id: uuid.UUID
    source_name: str
    due_on: date | None
    received_on: date | None
    version: int


@dataclass(frozen=True, slots=True)
class ItemRecord:
    id: uuid.UUID
    preparation_id: uuid.UUID
    text: str
    is_done: bool
    version: int


@dataclass(frozen=True, slots=True)
class PrepRecord:
    id: uuid.UUID
    kind: str
    title: str
    addressee: str | None
    show_on: date
    start_on: date | None
    responsible_id: uuid.UUID | None
    responsible_name: str | None
    stage: PrepStage
    project: tuple[uuid.UUID, str] | None
    moved_on: date
    """Последнее движение: правка подготовки, пункта или запроса (V41)."""

    version: int


def item_of(record: PrepRecord, awaiting_since: date | None) -> Item | None:
    """Строка лестницы: показ — срок, движение — признак жизни; прошедший показ закрыт."""
    if record.stage is PrepStage.SHOWN:
        return None
    return Item(
        section=SECTION,
        entity_id=record.id,
        title=record.title,
        due_on=record.show_on,
        last_sign_of_life=record.moved_on,
        awaiting_since=awaiting_since,
        lead_is_outside=False,
        responsible_person_id=record.responsible_id,
    )


def _latest(model: type[PreparationItem] | type[InfoRequest]) -> Subquery:
    return (
        select(
            model.preparation_id,
            func.max(func.coalesce(model.updated_at, model.created_at)).label("moved"),
        )
        .group_by(model.preparation_id)
        .subquery()
    )


async def records(
    session: AsyncSession,
    *,
    zone: ZoneInfo,
    open_only: bool = False,
    ids: list[uuid.UUID] | None = None,
) -> list[PrepRecord]:
    items = _latest(PreparationItem)
    requests = _latest(InfoRequest)
    statement = (
        select(Preparation, Person.full_name, Project.title, items.c.moved, requests.c.moved)
        .outerjoin(Person, Person.id == Preparation.responsible_person_id)
        .outerjoin(Project, Project.id == Preparation.project_id)
        .outerjoin(items, items.c.preparation_id == Preparation.id)
        .outerjoin(requests, requests.c.preparation_id == Preparation.id)
    )
    if open_only:
        statement = statement.where(Preparation.stage != PrepStage.SHOWN.value)
    if ids is not None:
        statement = statement.where(Preparation.id.in_(ids))
    rows = await session.execute(statement)
    found: list[PrepRecord] = []
    for prep, responsible, project_title, item_moved, request_moved in rows:
        moments: list[datetime] = [
            moment
            for moment in (prep.updated_at, prep.created_at, item_moved, request_moved)
            if moment is not None
        ]
        found.append(
            PrepRecord(
                id=prep.id,
                kind=prep.kind,
                title=prep.title,
                addressee=prep.addressee,
                show_on=prep.show_on,
                start_on=prep.start_on,
                responsible_id=prep.responsible_person_id,
                responsible_name=responsible,
                stage=PrepStage(prep.stage),
                project=(prep.project_id, project_title)
                if prep.project_id and project_title
                else None,
                moved_on=local_date(max(moments), zone),
                version=prep.version,
            )
        )
    return found


async def info_requests(
    session: AsyncSession, preparation_ids: list[uuid.UUID]
) -> list[RequestRecord]:
    if not preparation_ids:
        return []
    rows = await session.execute(
        select(InfoRequest, Person.full_name, Organization.short_name, Organization.name)
        .outerjoin(Person, Person.id == InfoRequest.source_person_id)
        .outerjoin(Organization, Organization.id == InfoRequest.source_organization_id)
        .where(InfoRequest.preparation_id.in_(preparation_ids))
        # По сроку: ближайший срок — выше; без срока — в конце.
        .order_by(InfoRequest.due_on.asc().nulls_last(), InfoRequest.created_at, InfoRequest.id)
    )
    found: list[RequestRecord] = []
    for request, person, short, organization in rows:
        is_person = request.source_person_id is not None
        found.append(
            RequestRecord(
                id=request.id,
                preparation_id=request.preparation_id,
                what=request.what,
                source_kind=SourceKind.PERSON if is_person else SourceKind.ORGANIZATION,
                source_id=request.source_person_id or request.source_organization_id,
                source_name=(person if is_person else (short or organization)) or "",
                due_on=request.due_on,
                received_on=request.received_on,
                version=request.version,
            )
        )
    return found


async def checklist(session: AsyncSession, preparation_ids: list[uuid.UUID]) -> list[ItemRecord]:
    if not preparation_ids:
        return []
    rows = await session.scalars(
        select(PreparationItem)
        .where(PreparationItem.preparation_id.in_(preparation_ids))
        .order_by(PreparationItem.sort_order, PreparationItem.created_at, PreparationItem.id)
    )
    return [
        ItemRecord(
            id=item.id,
            preparation_id=item.preparation_id,
            text=item.text,
            is_done=item.is_done,
            version=item.version,
        )
        for item in rows
    ]


async def projects(session: AsyncSession) -> list[tuple[uuid.UUID, str, str]]:
    """Проекты для выбора связи — код и название."""
    rows = await session.execute(
        select(Project.id, Project.code, Project.title).order_by(Project.code)
    )
    return list(rows.tuples())


async def organizations(session: AsyncSession) -> list[tuple[uuid.UUID, str, str | None]]:
    rows = await session.execute(
        select(Organization.id, Organization.name, Organization.short_name)
        .where(Organization.is_active.is_(True))
        .order_by(func.coalesce(Organization.short_name, Organization.name))
    )
    return list(rows.tuples())
