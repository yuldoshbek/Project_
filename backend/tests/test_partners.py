"""Организации-партнёры проекта (ORB-013).

Три критерия карточки. Третий — «поиск по названию организации находит связанные
проекты» — и есть смысл всей связи: без него список партнёров был бы украшением карточки,
а вопрос сценария U6 «что у нас с этой организацией» остался бы без ответа.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dictionaries import OrganizationKind, Priority, ProjectStatus
from app.repos.models import AuditLog, Direction, Organization, Project

pytestmark = pytest.mark.infra


async def a_project(session: AsyncSession, **overrides: Any) -> Project:
    direction = await session.scalar(select(Direction).limit(1))
    assert direction is not None
    fields: dict[str, Any] = {
        "code": f"PRJ-2026-{uuid.uuid4().int % 700 + 250:03d}",
        "title": "Проект с партнёрами",
        "kind": "project",
        "share_externally": True,
        "direction_id": direction.id,
        "status_code": ProjectStatus.IN_PROGRESS.value,
        "priority_code": Priority.NORMAL.value,
        "started_on": date(2026, 1, 1),
        "due_on": date(2026, 12, 31),
    }
    fields.update(overrides)
    project = Project(**fields)
    session.add(project)
    await session.flush()
    return project


async def an_organization(session: AsyncSession, **overrides: Any) -> Organization:
    fields: dict[str, Any] = {
        "name": "Европейское космическое агентство",
        "short_name": "ЕКА",
        "country_code": "FR",
        "kind": OrganizationKind.INTERNATIONAL.value,
    }
    fields.update(overrides)
    organization = Organization(**fields)
    session.add(organization)
    await session.flush()
    return organization


class TestSeveralPartnersWithRoles:
    async def test_a_project_takes_several_organizations_each_with_its_role(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        first = await an_organization(session)
        second = await an_organization(
            session,
            name="Министерство цифровых технологий",
            short_name="Мининфоком",
            country_code="UZ",
            kind=OrganizationKind.MINISTRY.value,
        )

        for organization, role in ((first, "соисполнитель"), (second, "заказчик")):
            added = await assistant_api.post(
                f"/api/v1/projects/{project.id}/partners",
                json={"organization_id": str(organization.id), "role": role},
            )
            assert added.status_code == 201, added.text

        listed = await assistant_api.get(f"/api/v1/projects/{project.id}/partners")

        assert [(item["organization"]["short_name"], item["role"]) for item in listed.json()] == [
            ("ЕКА", "соисполнитель"),
            ("Мининфоком", "заказчик"),
        ]

    async def test_the_organization_comes_with_its_name_not_just_an_identifier(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Иначе карточка проекта дозапрашивает каждое название отдельно."""
        project = await a_project(session)
        organization = await an_organization(session)

        added = await assistant_api.post(
            f"/api/v1/projects/{project.id}/partners",
            json={"organization_id": str(organization.id)},
        )

        assert added.json()["organization"]["name"] == "Европейское космическое агентство"
        assert added.json()["role"] is None, "роль необязательна"

    async def test_the_role_is_changed_in_place(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        organization = await an_organization(session)
        await assistant_api.post(
            f"/api/v1/projects/{project.id}/partners",
            json={"organization_id": str(organization.id), "role": "соисполнитель"},
        )

        changed = await assistant_api.patch(
            f"/api/v1/projects/{project.id}/partners/{organization.id}",
            json={"role": "головной исполнитель"},
        )

        assert changed.json()["role"] == "головной исполнитель"

    async def test_the_same_organization_cannot_be_attached_twice(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Две записи об одном партнёре — не «две роли», а ошибка ввода."""
        project = await a_project(session)
        organization = await an_organization(session)
        await assistant_api.post(
            f"/api/v1/projects/{project.id}/partners",
            json={"organization_id": str(organization.id)},
        )

        again = await assistant_api.post(
            f"/api/v1/projects/{project.id}/partners",
            json={"organization_id": str(organization.id), "role": "другая роль"},
        )

        assert again.status_code == 409
        assert "уже привязана" in again.json()["detail"]

    async def test_an_organization_is_detached(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        organization = await an_organization(session)
        await assistant_api.post(
            f"/api/v1/projects/{project.id}/partners",
            json={"organization_id": str(organization.id)},
        )

        removed = await assistant_api.delete(
            f"/api/v1/projects/{project.id}/partners/{organization.id}"
        )

        assert removed.status_code == 204
        assert (await assistant_api.get(f"/api/v1/projects/{project.id}/partners")).json() == []


class TestInternationalPartners:
    async def test_a_foreign_partner_keeps_its_country_and_short_name(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Международное сотрудничество — мандат агентства (ТЗ 3.1), а не частный случай."""
        project = await a_project(session)
        organization = await an_organization(
            session, name="Japan Aerospace Exploration Agency", short_name="JAXA", country_code="JP"
        )

        added = await assistant_api.post(
            f"/api/v1/projects/{project.id}/partners",
            json={"organization_id": str(organization.id), "role": "партнёр"},
        )

        body = added.json()["organization"]
        assert body["country_code"] == "JP"
        assert body["short_name"] == "JAXA"
        assert body["kind"] == OrganizationKind.INTERNATIONAL.value


class TestSearchFindsRelatedProjects:
    """Критерий 3: готовится к ORB-033, но отвечать должен уже сейчас."""

    async def test_projects_are_found_by_the_partner_identifier(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        with_partner = await a_project(session, title="Совместная программа")
        await a_project(session, title="Проект без партнёров")
        organization = await an_organization(session)
        await assistant_api.post(
            f"/api/v1/projects/{with_partner.id}/partners",
            json={"organization_id": str(organization.id)},
        )

        found = await assistant_api.get(
            "/api/v1/projects", params={"organization_id": str(organization.id)}
        )

        assert [item["title"] for item in found.json()] == ["Совместная программа"]

    async def test_projects_are_found_by_a_part_of_the_partner_name(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Вопрос сценария U6 звучит как «что у нас с ЕКА», а не как идентификатор."""
        with_partner = await a_project(session, title="Совместная программа")
        await a_project(session, title="Проект без партнёров")
        organization = await an_organization(session)
        await assistant_api.post(
            f"/api/v1/projects/{with_partner.id}/partners",
            json={"organization_id": str(organization.id)},
        )

        by_full_name = await assistant_api.get(
            "/api/v1/projects", params={"partner_search": "космическое"}
        )
        by_short_name = await assistant_api.get(
            "/api/v1/projects", params={"partner_search": "ЕКА"}
        )

        assert [item["title"] for item in by_full_name.json()] == ["Совместная программа"]
        assert [item["title"] for item in by_short_name.json()] == ["Совместная программа"]

    async def test_a_project_is_not_listed_twice_when_it_has_two_partners(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Соединение без подзапроса размножило бы проект по числу совпавших партнёров."""
        project = await a_project(session, title="Совместная программа")
        for name in ("Космический институт", "Космическое бюро"):
            organization = await an_organization(session, name=name, short_name=None)
            await assistant_api.post(
                f"/api/v1/projects/{project.id}/partners",
                json={"organization_id": str(organization.id)},
            )

        found = await assistant_api.get("/api/v1/projects", params={"partner_search": "космическ"})

        assert [item["title"] for item in found.json()] == ["Совместная программа"]


class TestFailures:
    async def test_attaching_to_a_missing_project_is_not_found(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        organization = await an_organization(session)

        response = await assistant_api.post(
            f"/api/v1/projects/{uuid.uuid4()}/partners",
            json={"organization_id": str(organization.id)},
        )

        assert response.status_code == 404

    async def test_attaching_a_missing_organization_is_not_found(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)

        response = await assistant_api.post(
            f"/api/v1/projects/{project.id}/partners",
            json={"organization_id": str(uuid.uuid4())},
        )

        assert response.status_code == 404

    async def test_changing_the_role_of_an_unlinked_organization_is_not_found(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        organization = await an_organization(session)

        response = await assistant_api.patch(
            f"/api/v1/projects/{project.id}/partners/{organization.id}",
            json={"role": "никто"},
        )

        assert response.status_code == 404

    async def test_detaching_an_unlinked_organization_is_not_found(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        organization = await an_organization(session)

        response = await assistant_api.delete(
            f"/api/v1/projects/{project.id}/partners/{organization.id}"
        )

        assert response.status_code == 404

    async def test_partners_of_a_missing_project_are_not_found(
        self, assistant_api: AsyncClient
    ) -> None:
        response = await assistant_api.get(f"/api/v1/projects/{uuid.uuid4()}/partners")

        assert response.status_code == 404


class TestWhoMayWrite:
    async def test_leader_reads_but_changes_nothing(
        self, leader_api: AsyncClient, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        organization = await an_organization(session)
        await assistant_api.post(
            f"/api/v1/projects/{project.id}/partners",
            json={"organization_id": str(organization.id)},
        )

        assert (await leader_api.get(f"/api/v1/projects/{project.id}/partners")).status_code == 200
        assert (
            await leader_api.post(
                f"/api/v1/projects/{project.id}/partners",
                json={"organization_id": str(organization.id)},
            )
        ).status_code == 403
        assert (
            await leader_api.patch(
                f"/api/v1/projects/{project.id}/partners/{organization.id}",
                json={"role": "правка"},
            )
        ).status_code == 403
        assert (
            await leader_api.delete(f"/api/v1/projects/{project.id}/partners/{organization.id}")
        ).status_code == 403


class TestJournal:
    async def test_attaching_a_partner_leaves_a_trail(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        organization = await an_organization(session)

        added = await assistant_api.post(
            f"/api/v1/projects/{project.id}/partners",
            json={"organization_id": str(organization.id), "role": "соисполнитель"},
        )
        assert added.status_code == 201

        entry = await session.scalar(
            select(AuditLog).where(AuditLog.entity_type == "project_partners")
        )
        assert entry is not None
        assert entry.action == "created"
        assert entry.changes["role"]["to"] == "соисполнитель"
