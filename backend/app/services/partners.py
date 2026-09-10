"""Организации-партнёры проекта: сценарии использования."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import ConflictError, NotFoundError
from app.repos.models import Organization, ProjectPartner
from app.services.projects import get as get_project


@dataclass(frozen=True, slots=True)
class PartnerView:
    """Связь вместе с организацией.

    Одним ответом, а не идентификатором и вторым запросом: в карточке проекта партнёров
    показывают названиями, и заставлять интерфейс дозапрашивать каждое — это столько же
    запросов, сколько партнёров.
    """

    link: ProjectPartner
    organization: Organization


async def list_for_project(session: AsyncSession, project_id: uuid.UUID) -> list[PartnerView]:
    await get_project(session, project_id)

    rows = await session.execute(
        select(ProjectPartner, Organization)
        .join(Organization, ProjectPartner.organization_id == Organization.id)
        .where(ProjectPartner.project_id == project_id)
        .order_by(Organization.name)
    )
    return [PartnerView(link=link, organization=organization) for link, organization in rows]


async def _link(
    session: AsyncSession, project_id: uuid.UUID, organization_id: uuid.UUID
) -> ProjectPartner:
    link = await session.scalar(
        select(ProjectPartner).where(
            ProjectPartner.project_id == project_id,
            ProjectPartner.organization_id == organization_id,
        )
    )
    if link is None:
        raise NotFoundError("Организация не привязана к этому проекту")
    return link


async def add(
    session: AsyncSession,
    project_id: uuid.UUID,
    organization_id: uuid.UUID,
    *,
    role: str | None,
) -> PartnerView:
    await get_project(session, project_id)

    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise NotFoundError("Организация не найдена")

    link = ProjectPartner(project_id=project_id, organization_id=organization_id, role=role)
    session.add(link)
    try:
        await session.flush()
    except IntegrityError as clash:
        # Уникальность ловится базой, а не проверкой перед вставкой: проверка перед
        # вставкой оставляет окно между чтением и записью, а здесь окна нет.
        raise ConflictError(
            "Эта организация уже привязана к проекту",
            detail="роль указывается в существующей связи, а не второй записью",
        ) from clash

    return PartnerView(link=link, organization=organization)


async def set_role(
    session: AsyncSession,
    project_id: uuid.UUID,
    organization_id: uuid.UUID,
    *,
    role: str | None,
) -> PartnerView:
    link = await _link(session, project_id, organization_id)
    link.role = role
    await session.flush()

    organization = await session.get(Organization, organization_id)
    assert organization is not None
    return PartnerView(link=link, organization=organization)


async def remove(session: AsyncSession, project_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    link = await _link(session, project_id, organization_id)
    await session.delete(link)
    await session.flush()
