"""Справочники.

Главное здесь — два вида расхождений, которые не видны на ревью и всплывают на приёмке:
между кодом и данными (перечисление есть, строки нет) и между локалями (на узбекской
версии интерфейса появляется русское слово).
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import seed as seed_module
from app.domain.dictionaries import Priority, ProjectStatus, SettingKey, TaskStatus
from app.repos.models import Direction, PriorityRef, ProjectStatusRef, Setting, TaskStatusRef
from app.services import dictionaries as service

pytestmark = pytest.mark.infra

DICTIONARY_MODELS = (Direction, ProjectStatusRef, TaskStatusRef, PriorityRef)


class TestSeededContent:
    async def test_all_directions_from_tz_are_present(self, session: AsyncSession) -> None:
        """Стартовый набор направлений — из мандата агентства (ТЗ 7, 3.1)."""
        codes = set(await session.scalars(select(Direction.code)))

        assert codes == {
            "space_monitoring",
            "remote_sensing",
            "international",
            "infrastructure",
            "regulatory",
            "internal",
        }

    @pytest.mark.parametrize("model", DICTIONARY_MODELS, ids=lambda m: m.__tablename__)
    async def test_all_three_scripts_are_filled(self, session: AsyncSession, model: Any) -> None:
        """Незаполненный перевод — это русское слово в узбекском интерфейсе (ТЗ 10.3)."""
        rows = list(await session.scalars(select(model)))

        assert rows, f"справочник {model.__tablename__} пуст"
        for row in rows:
            for field in ("name_ru", "name_uz_cyrl", "name_uz_latn"):
                assert getattr(row, field).strip(), (
                    f"{model.__tablename__}.{row.code}: пусто {field}"
                )

    @pytest.mark.parametrize(
        ("model", "enum_type"),
        [
            (ProjectStatusRef, ProjectStatus),
            (TaskStatusRef, TaskStatus),
            (PriorityRef, Priority),
        ],
        ids=["project_statuses", "task_statuses", "priorities"],
    )
    async def test_codes_match_domain_enums(
        self, session: AsyncSession, model: Any, enum_type: Any
    ) -> None:
        """Код и данные не разошлись.

        Значение перечисления без строки в справочнике означает статус без названия;
        строка без значения — статус, смысла которого система не знает. И то и другое
        обнаруживается на экране у пользователя, а не здесь, если этой проверки нет.
        """
        in_database = set(await session.scalars(select(model.code)))
        in_code = {str(member) for member in enum_type}

        assert in_database == in_code

    async def test_overdue_is_not_a_task_status(self, session: AsyncSession) -> None:
        """«Просрочена» из ТЗ 7 — вычисляемый признак, а не состояние работы (ADR-0004)."""
        names = set(await session.scalars(select(TaskStatusRef.name_ru)))

        assert "Просрочена" not in names

    async def test_urgent_priority_turns_yellow_immediately(self, session: AsyncSession) -> None:
        """У «Срочно» порог жёлтой зоны равен нулю (ADR-0005), и это данные, а не код."""
        override = await session.scalar(
            select(PriorityRef.warn_days_override).where(PriorityRef.code == Priority.URGENT)
        )
        normal = await session.scalar(
            select(PriorityRef.warn_days_override).where(PriorityRef.code == Priority.NORMAL)
        )

        assert override == 0
        assert normal is None, "у обычного приоритета порог общий, из настроек"

    async def test_settings_cover_every_known_key(self, session: AsyncSession) -> None:
        """Параметр, известный коду, но отсутствующий в базе, читался бы как пустой."""
        stored = set(await session.scalars(select(Setting.key)))

        assert stored == {str(key) for key in SettingKey}

    async def test_status_flags_match_domain_rules(self, session: AsyncSession) -> None:
        """Флаги в справочнике совпадают с правилами домена."""
        rows = list(await session.scalars(select(ProjectStatusRef)))

        for row in rows:
            status = ProjectStatus(row.code)
            assert row.is_terminal == status.is_terminal, row.code
            assert row.requires_reason == status.requires_reason, row.code


class TestSeedBehaviour:
    async def test_second_run_adds_nothing(self, session: AsyncSession) -> None:
        added = await seed_module.seed(session)

        assert added == dict.fromkeys(added, 0)

    async def test_edits_survive_re_seeding(self, session: AsyncSession) -> None:
        """Правки помощника переживают обновление системы.

        Сиды, затирающие изменения, превратили бы редактируемый справочник в декорацию —
        а ТЗ 6.8 требует ровно обратного.
        """
        await session.execute(
            update(ProjectStatusRef)
            .where(ProjectStatusRef.code == ProjectStatus.AWAITING_DECISION)
            .values(name_ru="Ждёт решения замдиректора", sort_order=99)
        )

        await seed_module.seed(session)

        row = await session.scalar(
            select(ProjectStatusRef).where(ProjectStatusRef.code == ProjectStatus.AWAITING_DECISION)
        )
        assert row is not None
        assert row.name_ru == "Ждёт решения замдиректора"
        assert row.sort_order == 99

    async def test_seed_does_not_duplicate_on_empty_database(self, session: AsyncSession) -> None:
        await seed_module.seed(session)
        await seed_module.seed(session)

        total = await session.scalar(select(func.count()).select_from(Direction))
        assert total == len(seed_module.DIRECTIONS)


class TestReading:
    async def test_deactivated_entry_hides_from_forms_but_stays_visible(
        self, session: AsyncSession
    ) -> None:
        """Отключённое направление нельзя выбрать заново, но старый проект его показывает.

        Удалять значение, на которое ссылаются записи, нельзя — иначе из карточки исчезнет
        направление, по которому проект когда-то завели (критерий ORB-010).
        """
        await session.execute(
            update(Direction).where(Direction.code == "internal").values(is_active=False)
        )

        for_forms = await service.load_dictionaries(session, active_only=True)
        for_display = await service.load_dictionaries(session, active_only=False)

        assert "internal" not in {item.code for item in for_forms.directions}
        assert "internal" in {item.code for item in for_display.directions}

    async def test_entries_come_in_configured_order(self, session: AsyncSession) -> None:
        """Порядок задаёт помощник, а не база: без сортировки он был бы случайным."""
        loaded = await service.load_dictionaries(session)

        orders = [item.sort_order for item in loaded.project_statuses]
        assert orders == sorted(orders)
        assert loaded.project_statuses[0].code == ProjectStatus.INITIATION

    async def test_missing_setting_falls_back_to_default(self, session: AsyncSession) -> None:
        """Незаполненный параметр не должен ронять систему."""
        value = await service.get_setting(session, SettingKey.WARN_DAYS, default=3)

        assert value == 3


class TestApi:
    async def test_dictionaries_come_in_all_three_scripts(self, api: AsyncClient) -> None:
        """Ответ содержит все три письменности сразу.

        Иначе переключение языка потребовало бы нового запроса, а по ORB-005 язык
        меняется без перезагрузки.
        """
        response = await api.get("/api/v1/dictionaries")

        assert response.status_code == 200
        body = response.json()
        assert len(body["directions"]) == 6

        first = body["directions"][0]
        assert set(first["name"]) == {"ru", "uz_cyrl", "uz_latn"}
        assert all(value.strip() for value in first["name"].values())

    async def test_dictionaries_carry_flags_needed_by_the_interface(self, api: AsyncClient) -> None:
        body = (await api.get("/api/v1/dictionaries")).json()

        awaiting = next(
            item for item in body["project_statuses"] if item["code"] == "awaiting_decision"
        )
        assert awaiting["color"]
        assert awaiting["is_terminal"] is False

        urgent = next(item for item in body["priorities"] if item["code"] == "urgent")
        assert urgent["warn_days_override"] == 0

    async def test_settings_are_readable(self, api: AsyncClient) -> None:
        body = (await api.get("/api/v1/settings")).json()

        assert body[SettingKey.WARN_DAYS] == 3
        assert body[SettingKey.STAGNATION_DAYS] == 14
        assert body[SettingKey.REMINDER_DAYS] == [1, 3, 7]

    async def test_organizations_are_empty_until_entered(self, api: AsyncClient) -> None:
        """Организации сидами не заполняются: их вносит помощник по реальным партнёрам."""
        response = await api.get("/api/v1/organizations")

        assert response.status_code == 200
        assert response.json() == []
