"""Строка «что мешает» (ORB-073).

Единственное поле ручного ввода по рискам
([ADR-0016](../../docs/adr/ADR-0016-risks-signals-not-register.md)). Реестра рисков с
вероятностью, влиянием и планом реагирования нет и не будет — и первый тест проверяет
именно это: не то, что поле работает, а то, что рядом с ним ничего не завелось.

Второе по важности — устаревание. Запись месячной давности говорит не о препятствии, а о
том, что её забыли обновить. Считать её за действующую проблему значит держать на главном
экране тревогу, которой, возможно, давно нет, и приучить не обращать на тревогу внимания.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dictionaries import Priority, ProjectStatus, SettingKey
from app.domain.projects import (
    DEFAULT_IMPEDIMENT_STALE_DAYS,
    has_active_impediment,
    impediment_is_stale,
)
from app.repos.models import AuditLog, Direction, Project, Setting

pytestmark = pytest.mark.infra

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


class TestNothingElseCameWithIt:
    def test_there_is_no_risk_register_in_the_schema(self) -> None:
        """Ни вероятности, ни влияния, ни плана реагирования — прямо из критерия.

        Реестр рисков требует регулярного пересмотра руками, которого при одном вносящем
        человеке не случится: через квартал это кладбище записей, которым никто не верит.
        """
        columns = set(Project.__table__.columns.keys())

        assert "impediment" in columns
        assert "impediment_updated_at" in columns
        assert not columns & {
            "risk_probability",
            "risk_impact",
            "risk_response",
            "risk_level",
            "mitigation_plan",
        }

    def test_the_impediment_is_one_text_field_not_a_table(self) -> None:
        from app.repos import models

        assert not hasattr(models, "Risk"), "реестра рисков быть не должно"


class TestStaleness:
    @pytest.mark.parametrize(
        ("age_days", "stale", "why"),
        [
            (0, False, "только что записали"),
            (13, False, "почти порог"),
            (14, False, "ровно порог — ещё свежая"),
            (15, True, "перевалило за порог"),
        ],
    )
    def test_boundaries(self, age_days: int, stale: bool, why: str) -> None:
        updated = NOW - timedelta(days=age_days)

        assert (
            impediment_is_stale(
                updated_at=updated, now=NOW, stale_days=DEFAULT_IMPEDIMENT_STALE_DAYS
            )
            is stale
        ), why

    def test_an_absent_date_is_not_stale(self) -> None:
        """Строки нет — и устаревать нечему."""
        assert impediment_is_stale(updated_at=None, now=NOW, stale_days=14) is False

    @pytest.mark.parametrize(
        ("text", "age_days", "active", "why"),
        [
            ("Ждём подписания соглашения", 1, True, "свежая запись — действующая помеха"),
            ("Ждём подписания соглашения", 40, False, "устарела: забыли обновить"),
            ("   ", 1, False, "пробелы помехой не считаются"),
            (None, 1, False, "пустая строка — не помеха"),
        ],
    )
    def test_only_a_fresh_and_filled_line_counts_as_a_problem(
        self, text: str | None, age_days: int, active: bool, why: str
    ) -> None:
        assert (
            has_active_impediment(
                impediment=text,
                updated_at=NOW - timedelta(days=age_days),
                now=NOW,
                stale_days=DEFAULT_IMPEDIMENT_STALE_DAYS,
            )
            is active
        ), why


async def a_project(session: AsyncSession, **overrides: Any) -> Project:
    direction = await session.scalar(select(Direction).limit(1))
    assert direction is not None
    fields: dict[str, Any] = {
        "code": f"PRJ-2026-{uuid.uuid4().int % 600 + 350:03d}",
        "title": "Проект с помехой",
        "kind": "project",
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


class TestTheEndpoint:
    async def test_the_line_is_written_and_the_date_is_set_by_the_system(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)

        response = await assistant_api.patch(
            f"/api/v1/projects/{project.id}/impediment",
            json={"impediment": "Ждём подписания межведомственного соглашения"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["impediment"] == "Ждём подписания межведомственного соглашения"
        assert body["impediment_updated_at"] is not None, "дата обязана прийти вместе с текстом"
        assert body["impediment_is_stale"] is False
        assert body["impediment_is_active"] is True

    async def test_the_date_cannot_be_set_by_hand(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Дата, которой можно управлять, перестаёт отвечать на вопрос «насколько свежо»."""
        project = await a_project(session)
        forged = (datetime.now(UTC) + timedelta(days=365)).isoformat()

        response = await assistant_api.patch(
            f"/api/v1/projects/{project.id}/impediment",
            json={"impediment": "Помеха", "impediment_updated_at": forged},
        )

        assert response.status_code == 200
        assert response.json()["impediment_updated_at"] != forged

    async def test_the_general_project_patch_cannot_touch_the_line(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Иначе помеху отметили бы свежей заодно с правкой названия, ничего о ней не узнав."""
        project = await a_project(session)

        response = await assistant_api.patch(
            f"/api/v1/projects/{project.id}",
            json={"title": "Новое название", "impediment": "Проникло через общий эндпоинт"},
        )

        assert response.status_code == 200
        assert response.json()["impediment"] is None

        await session.refresh(project)
        assert project.impediment is None

    async def test_repeating_the_line_refreshes_the_date(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Обращение сюда — подтверждение, что помеха всё ещё та же и всё ещё есть.

        Именно на этот вопрос дата и отвечает, поэтому подтверждение её обновляет.
        """
        project = await a_project(session)
        first = await assistant_api.patch(
            f"/api/v1/projects/{project.id}/impediment", json={"impediment": "Та же помеха"}
        )
        project.impediment_updated_at = datetime.now(UTC) - timedelta(days=30)
        await session.flush()

        second = await assistant_api.patch(
            f"/api/v1/projects/{project.id}/impediment", json={"impediment": "Та же помеха"}
        )

        assert second.json()["impediment_updated_at"] > first.json()["impediment_updated_at"]
        assert second.json()["impediment_is_stale"] is False

    async def test_clearing_the_line_clears_the_date(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Дата без текста ничего не датирует."""
        project = await a_project(session)
        await assistant_api.patch(
            f"/api/v1/projects/{project.id}/impediment", json={"impediment": "Помеха"}
        )

        cleared = await assistant_api.patch(
            f"/api/v1/projects/{project.id}/impediment", json={"impediment": None}
        )

        assert cleared.json()["impediment"] is None
        assert cleared.json()["impediment_updated_at"] is None
        assert cleared.json()["impediment_is_active"] is False

    async def test_a_stale_line_is_shown_but_not_counted(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Текст и дату видно всегда; действующей проблемой запись быть перестаёт."""
        project = await a_project(session)
        await assistant_api.patch(
            f"/api/v1/projects/{project.id}/impediment", json={"impediment": "Старая помеха"}
        )
        project.impediment_updated_at = datetime.now(UTC) - timedelta(days=40)
        await session.flush()

        card = await assistant_api.get(f"/api/v1/projects/{project.id}")

        assert card.json()["impediment"] == "Старая помеха"
        assert card.json()["impediment_updated_at"] is not None
        assert card.json()["impediment_is_stale"] is True
        assert card.json()["impediment_is_active"] is False

    async def test_the_threshold_comes_from_the_settings_and_changes_without_a_developer(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """ТЗ 6.8: пороги редактируются, а не зашиваются."""
        project = await a_project(session)
        await assistant_api.patch(
            f"/api/v1/projects/{project.id}/impediment", json={"impediment": "Помеха"}
        )
        project.impediment_updated_at = datetime.now(UTC) - timedelta(days=5)
        await session.flush()

        assert (await assistant_api.get(f"/api/v1/projects/{project.id}")).json()[
            "impediment_is_stale"
        ] is False

        setting = await session.scalar(
            select(Setting).where(Setting.key == SettingKey.IMPEDIMENT_STALE_DAYS.value)
        )
        assert setting is not None, "порог обязан быть в справочнике, а не в коде"
        setting.value = 3
        await session.flush()

        assert (await assistant_api.get(f"/api/v1/projects/{project.id}")).json()[
            "impediment_is_stale"
        ] is True

    async def test_the_line_is_visible_in_the_portfolio_list(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session, title="С помехой")
        await assistant_api.patch(
            f"/api/v1/projects/{project.id}/impediment",
            json={"impediment": "Нет ответа от партнёра"},
        )

        listed = await assistant_api.get("/api/v1/projects", params={"search": "С помехой"})

        assert listed.json()[0]["impediment"] == "Нет ответа от партнёра"
        assert listed.json()[0]["impediment_is_active"] is True


class TestWhoMayWrite:
    async def test_the_leader_cannot_write_the_line(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)

        response = await leader_api.patch(
            f"/api/v1/projects/{project.id}/impediment", json={"impediment": "Помеха"}
        )

        assert response.status_code == 403


class TestJournal:
    async def test_the_line_change_leaves_a_trail(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)

        await assistant_api.patch(
            f"/api/v1/projects/{project.id}/impediment", json={"impediment": "Помеха"}
        )

        entries = list(
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.entity_id == project.id)
                .order_by(AuditLog.occurred_at)
            )
        )
        assert entries[-1].action == "updated"
        assert entries[-1].changes["impediment"]["to"] == "Помеха"
        assert "impediment_updated_at" in entries[-1].changes
