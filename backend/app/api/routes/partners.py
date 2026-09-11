"""Организации-партнёры проекта.

Партнёр приходит вместе с названием организации, а не одним идентификатором: в карточке
проекта их показывают названиями, и дозапрашивать каждое — это столько же запросов,
сколько партнёров.

Обратный вопрос — «в каких проектах участвует эта организация» — отвечается фильтрами
`organization_id` и `partner_search` на `GET /projects`: он про портфель, а не про
карточку, и жить ему там.
"""

from __future__ import annotations

import uuid

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep
from app.api.security import Assistant, get_active_user
from app.api.transaction import transactional_router
from app.services import partners as service

router = transactional_router(tags=["партнёры"], dependencies=[Depends(get_active_user)])

ROLE_MAX = 100


class PartnerOrganization(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    short_name: str | None
    country_code: str | None
    kind: str


class PartnerResponse(BaseModel):
    project_id: uuid.UUID
    organization: PartnerOrganization
    role: str | None

    @classmethod
    def of(cls, item: service.PartnerView) -> PartnerResponse:
        return cls(
            project_id=item.link.project_id,
            organization=PartnerOrganization.model_validate(item.organization),
            role=item.link.role,
        )


class PartnerCreate(BaseModel):
    organization_id: uuid.UUID
    role: str | None = Field(default=None, max_length=ROLE_MAX)


class PartnerRole(BaseModel):
    role: str | None = Field(default=None, max_length=ROLE_MAX)


@router.get(
    "/projects/{project_id}/partners",
    response_model=list[PartnerResponse],
    summary="Партнёры проекта",
)
async def list_partners(project_id: uuid.UUID, session: SessionDep) -> list[PartnerResponse]:
    rows = await service.list_for_project(session, project_id)
    return [PartnerResponse.of(item) for item in rows]


@router.post(
    "/projects/{project_id}/partners",
    response_model=PartnerResponse,
    status_code=201,
    summary="Привязка организации к проекту",
)
async def add_partner(
    project_id: uuid.UUID, payload: PartnerCreate, session: SessionDep, user: Assistant
) -> PartnerResponse:
    item = await service.add(session, project_id, payload.organization_id, role=payload.role)
    return PartnerResponse.of(item)


@router.patch(
    "/projects/{project_id}/partners/{organization_id}",
    response_model=PartnerResponse,
    summary="Роль партнёра",
)
async def set_partner_role(
    project_id: uuid.UUID,
    organization_id: uuid.UUID,
    payload: PartnerRole,
    session: SessionDep,
    user: Assistant,
) -> PartnerResponse:
    item = await service.set_role(session, project_id, organization_id, role=payload.role)
    return PartnerResponse.of(item)


@router.delete(
    "/projects/{project_id}/partners/{organization_id}",
    status_code=204,
    summary="Отвязка организации",
)
async def remove_partner(
    project_id: uuid.UUID, organization_id: uuid.UUID, session: SessionDep, user: Assistant
) -> None:
    await service.remove(session, project_id, organization_id)
