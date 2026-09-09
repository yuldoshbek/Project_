"""Справочники: чтение.

Ответ содержит названия **на всех трёх письменностях сразу**, а не на выбранной. Так
переключение языка в интерфейсе не требует нового запроса — а это прямое требование
ORB-005: язык меняется без перезагрузки.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from app.api.deps import SessionDep
from app.services import dictionaries as service

router = APIRouter(tags=["справочники"])


class LocalizedNames(BaseModel):
    ru: str
    uz_cyrl: str
    uz_latn: str


class DictionaryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: LocalizedNames
    sort_order: int
    is_active: bool

    @classmethod
    def of(cls, entry: Any) -> DictionaryItem:
        return cls(
            id=entry.id,
            code=entry.code,
            name=LocalizedNames(
                ru=entry.name_ru,
                uz_cyrl=entry.name_uz_cyrl,
                uz_latn=entry.name_uz_latn,
            ),
            sort_order=entry.sort_order,
            is_active=entry.is_active,
        )


class StatusItem(DictionaryItem):
    color: str
    is_terminal: bool


class ProjectStatusItem(StatusItem):
    requires_reason: bool


class PriorityItem(DictionaryItem):
    color: str
    warn_days_override: int | None


class DictionariesResponse(BaseModel):
    directions: list[DictionaryItem]
    project_statuses: list[ProjectStatusItem]
    task_statuses: list[StatusItem]
    priorities: list[PriorityItem]


class OrganizationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    short_name: str | None
    country_code: str | None
    kind: str
    is_active: bool


@router.get("/dictionaries", response_model=DictionariesResponse, summary="Все справочники")
async def read_dictionaries(
    session: SessionDep,
    active_only: bool = Query(
        default=True,
        description=(
            "Только действующие значения. Для форм создания — да; при показе старой "
            "записи — нет, иначе исчезнет направление, по которому её когда-то завели."
        ),
    ),
) -> DictionariesResponse:
    loaded = await service.load_dictionaries(session, active_only=active_only)

    return DictionariesResponse(
        directions=[DictionaryItem.of(item) for item in loaded.directions],
        project_statuses=[
            ProjectStatusItem(
                **DictionaryItem.of(item).model_dump(),
                color=item.color,
                is_terminal=item.is_terminal,
                requires_reason=item.requires_reason,
            )
            for item in loaded.project_statuses
        ],
        task_statuses=[
            StatusItem(
                **DictionaryItem.of(item).model_dump(),
                color=item.color,
                is_terminal=item.is_terminal,
            )
            for item in loaded.task_statuses
        ],
        priorities=[
            PriorityItem(
                **DictionaryItem.of(item).model_dump(),
                color=item.color,
                warn_days_override=item.warn_days_override,
            )
            for item in loaded.priorities
        ],
    )


@router.get(
    "/organizations",
    response_model=list[OrganizationItem],
    summary="Организации-партнёры",
)
async def read_organizations(
    session: SessionDep,
    active_only: bool = Query(default=True),
    search: str | None = Query(default=None, description="Совпадение по части названия"),
) -> list[OrganizationItem]:
    rows = await service.list_organizations(session, active_only=active_only, search=search)
    return [OrganizationItem.model_validate(row) for row in rows]


@router.get("/settings", summary="Настраиваемые параметры системы")
async def read_settings(session: SessionDep) -> dict[str, Any]:
    """Пороги светофора, интервалы напоминаний, время сводки.

    Не путать с настройками окружения: те задаёт тот, кто разворачивает систему, эти
    меняет помощник (ТЗ 6.8).
    """
    return await service.load_settings(session)
