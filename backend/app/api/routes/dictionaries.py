"""Справочники: чтение.

Ответ содержит названия **на всех трёх письменностях сразу**, а не на выбранной. Так
переключение языка в интерфейсе не требует нового запроса — а узбекская латиница и
кириллица приезжают в блоке 3, и машинерия должна быть готова заранее (ТЗ 6).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict

from app.api.deps import SessionDep
from app.api.security import get_current_user
from app.api.transaction import transactional_router
from app.services import dictionaries as service

# Требование входа объявлено на роутере, а не на каждом обработчике: забыть его на одном
# новом эндпоинте — значит открыть данные агентства анонимно.
router = transactional_router(tags=["справочники"], dependencies=[Depends(get_current_user)])


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


class DictionariesResponse(BaseModel):
    project_types: list[DictionaryItem]
    task_types: list[DictionaryItem]
    directions: list[DictionaryItem]
    regions: list[DictionaryItem]
    project_statuses: list[ProjectStatusItem]
    task_statuses: list[StatusItem]


class MilestoneTemplateItem(BaseModel):
    """Веха шаблона: что подставится в новый проект этого типа."""

    id: uuid.UUID
    name: LocalizedNames
    offset_days: int
    sort_order: int


class OrganizationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    short_name: str | None
    kind: str
    is_founded_by_agency: bool
    country_code: str | None
    is_active: bool


ACTIVE_ONLY = Query(
    default=True,
    description=(
        "Только действующие значения. Для форм создания — да; при показе старой записи "
        "— нет, иначе исчезнет тип, по которому её когда-то завели."
    ),
)


@router.get("/dictionaries", response_model=DictionariesResponse, summary="Все справочники")
async def read_dictionaries(
    session: SessionDep, active_only: bool = ACTIVE_ONLY
) -> DictionariesResponse:
    loaded = await service.load_dictionaries(session, active_only=active_only)

    return DictionariesResponse(
        project_types=[DictionaryItem.of(item) for item in loaded.project_types],
        task_types=[DictionaryItem.of(item) for item in loaded.task_types],
        directions=[DictionaryItem.of(item) for item in loaded.directions],
        regions=[DictionaryItem.of(item) for item in loaded.regions],
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
    )


@router.get(
    "/project-types/{project_type_id}/milestones",
    response_model=list[MilestoneTemplateItem],
    summary="Шаблон вех типа проекта",
)
async def read_milestone_template(
    project_type_id: uuid.UUID, session: SessionDep
) -> list[MilestoneTemplateItem]:
    return [
        MilestoneTemplateItem(
            id=item.id,
            name=LocalizedNames(
                ru=item.name_ru, uz_cyrl=item.name_uz_cyrl, uz_latn=item.name_uz_latn
            ),
            offset_days=item.offset_days,
            sort_order=item.sort_order,
        )
        for item in await service.milestone_template(session, project_type_id)
    ]


@router.get("/organizations", response_model=list[OrganizationItem], summary="Организации")
async def read_organizations(
    session: SessionDep,
    active_only: bool = ACTIVE_ONLY,
    search: str | None = Query(default=None, description="Совпадение по части названия"),
    founded_by_agency: bool | None = Query(
        default=None, description="Только учреждённые агентством — срез «что держит Центр»"
    ),
) -> list[OrganizationItem]:
    rows = await service.list_organizations(
        session, active_only=active_only, search=search, founded_by_agency=founded_by_agency
    )
    return [OrganizationItem.model_validate(row) for row in rows]


@router.get("/settings", summary="Пороги сигналов")
async def read_settings(session: SessionDep) -> dict[str, Any]:
    """Пороги «горит», «молчит» и прочие (ТЗ 4).

    Не путать с переменными окружения: те задаёт тот, кто разворачивает систему, эти
    меняет помощник без выкладки.
    """
    return await service.load_settings(session)
