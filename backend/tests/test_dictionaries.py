"""Справочники (ТЗ 3.9).

Главное здесь — два вида расхождений, которые не видны на ревью и всплывают на приёмке:
между кодом и данными (перечисление есть, строки нет) и между локалями (на узбекской
версии интерфейса появляется русское слово).

Числа в проверках состава — из ТЗ, а не из `app.seed`: сверка наполнения с самим собой
ничего бы не поймала.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import seed as seed_module
from app.domain.dictionaries import ProjectStatus, SettingKey, TaskStatus
from app.domain.people import Role
from app.repos.models import (
    Direction,
    Organization,
    ProjectStatusRef,
    ProjectTypeMilestone,
    ProjectTypeRef,
    Region,
    Setting,
    TaskStatusRef,
    TaskTypeRef,
    User,
)
from app.services import dictionaries as service

pytestmark = pytest.mark.infra

DICTIONARY_MODELS = (
    ProjectTypeRef,
    TaskTypeRef,
    Direction,
    Region,
    ProjectStatusRef,
    TaskStatusRef,
)


class TestSeededContent:
    @pytest.mark.parametrize(
        ("model", "expected"),
        [(ProjectTypeRef, 10), (TaskTypeRef, 11), (Region, 14), (Direction, 6)],
        ids=["project_types", "task_types", "regions", "directions"],
    )
    async def test_composition_matches_tz(
        self, session: AsyncSession, model: Any, expected: int
    ) -> None:
        """10 типов проектов и 11 типов задач (ТЗ 3.9), 14 административных единиц (ТЗ 3.1).

        Регионов 14: двенадцать областей, Республика Каракалпакстан и город Ташкент.
        """
        total = await session.scalar(select(func.count()).select_from(model))

        assert total == expected

    @pytest.mark.parametrize("model", DICTIONARY_MODELS, ids=lambda m: m.__tablename__)
    async def test_all_three_scripts_are_filled(self, session: AsyncSession, model: Any) -> None:
        """Незаполненный перевод — это русское слово в узбекском интерфейсе."""
        rows = list(await session.scalars(select(model)))

        assert rows, f"справочник {model.__tablename__} пуст"
        for row in rows:
            for field in ("name_ru", "name_uz_cyrl", "name_uz_latn"):
                assert getattr(row, field).strip(), (
                    f"{model.__tablename__}.{row.code}: пусто {field}"
                )

    @pytest.mark.parametrize(
        ("model", "enum_type"),
        [(ProjectStatusRef, ProjectStatus), (TaskStatusRef, TaskStatus)],
        ids=["project_statuses", "task_statuses"],
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

    async def test_overdue_is_not_a_status(self, session: AsyncSession) -> None:
        """«Просрочено» и «ждёт решения» вычисляются, а не хранятся (инвариант 1)."""
        codes = set(await session.scalars(select(ProjectStatusRef.code))) | set(
            await session.scalars(select(TaskStatusRef.code))
        )

        assert not codes & {"overdue", "awaiting_decision"}

    async def test_every_project_type_has_a_milestone_template(self, session: AsyncSession) -> None:
        """Ради шаблона вех типы проектов и заводятся (ТЗ 3.1): тип без шаблона — пустышка.

        Сроки вех в шаблоне идут по порядку: веха, наступающая раньше предыдущей, дала бы
        новому проекту план, который нарушен в день создания.
        """
        types = list(await session.scalars(select(ProjectTypeRef)))
        for project_type in types:
            steps = list(
                await session.scalars(
                    select(ProjectTypeMilestone)
                    .where(ProjectTypeMilestone.project_type_id == project_type.id)
                    .order_by(ProjectTypeMilestone.sort_order)
                )
            )
            assert steps, f"у типа {project_type.code} нет шаблона вех"
            offsets = [step.offset_days for step in steps]
            assert offsets == sorted(offsets), f"{project_type.code}: вехи не по порядку"

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

    async def test_exactly_one_user_per_role(self, session: AsyncSession) -> None:
        """Пользователей двое, по одному на роль (ТЗ 1.1)."""
        roles = list(await session.scalars(select(User.role)))

        assert sorted(roles) == sorted(role.value for role in Role)

    async def test_center_is_founded_by_agency(self, session: AsyncSession) -> None:
        """Без признака у Центра срез «что держит Центр» пуст (ТЗ 5)."""
        center = await session.scalar(
            select(Organization).where(Organization.name == seed_module.CENTER_NAME)
        )

        assert center is not None
        assert center.is_founded_by_agency is True


class TestSeedBehaviour:
    async def test_second_run_adds_nothing(self, session: AsyncSession) -> None:
        added = await seed_module.seed(session)

        assert added == dict.fromkeys(added, 0)

    async def test_edits_survive_re_seeding(self, session: AsyncSession) -> None:
        """Правки помощника переживают обновление системы.

        Наполнение, затирающее изменения, превратило бы редактируемый справочник в
        декорацию — а ТЗ 3.9 требует ровно обратного.
        """
        await session.execute(
            update(ProjectStatusRef)
            .where(ProjectStatusRef.code == ProjectStatus.ON_HOLD)
            .values(name_ru="Отложен до решения", sort_order=99)
        )

        await seed_module.seed(session)

        row = await session.scalar(
            select(ProjectStatusRef).where(ProjectStatusRef.code == ProjectStatus.ON_HOLD)
        )
        assert row is not None
        assert row.name_ru == "Отложен до решения"
        assert row.sort_order == 99

    async def test_template_edits_survive_re_seeding(self, session: AsyncSession) -> None:
        """Удалённая помощником веха шаблона не возвращается при обновлении системы.

        Ключ шаблона — пара «тип + порядок»: наполнение узнаёт по ней заведённую веху, а
        правку названия считает правкой, а не новой строкой.
        """
        step = await session.scalar(select(ProjectTypeMilestone).limit(1))
        assert step is not None
        step.name_ru = "Своя формулировка помощника"
        await session.flush()

        await seed_module.seed(session)

        same = await session.scalar(
            select(ProjectTypeMilestone).where(
                ProjectTypeMilestone.project_type_id == step.project_type_id,
                ProjectTypeMilestone.sort_order == step.sort_order,
            )
        )
        assert same is not None
        assert same.name_ru == "Своя формулировка помощника"

    async def test_seed_does_not_duplicate(self, session: AsyncSession) -> None:
        await seed_module.seed(session)
        await seed_module.seed(session)

        for model, rows in (
            (Direction, seed_module.DIRECTIONS),
            (Region, seed_module.REGIONS),
            (ProjectTypeRef, seed_module.PROJECT_TYPES),
            (TaskTypeRef, seed_module.TASK_TYPES),
            (Organization, seed_module.ORGANIZATIONS),
        ):
            total = await session.scalar(select(func.count()).select_from(model))
            assert total == len(rows), model.__tablename__

        steps = await session.scalar(select(func.count()).select_from(ProjectTypeMilestone))
        assert steps == sum(len(each) for each in seed_module.MILESTONE_TEMPLATES.values())


class TestReading:
    async def test_deactivated_entry_hides_from_forms_but_stays_visible(
        self, session: AsyncSession
    ) -> None:
        """Отключённый тип нельзя выбрать заново, но старый проект его показывает.

        Удалять значение, на которое ссылаются записи, нельзя — иначе из карточки исчезнет
        тип, по которому проект когда-то завели.
        """
        target = await session.scalar(select(ProjectTypeRef.code).limit(1))
        assert target is not None
        await session.execute(
            update(ProjectTypeRef).where(ProjectTypeRef.code == target).values(is_active=False)
        )

        for_forms = await service.load_dictionaries(session, active_only=True)
        for_display = await service.load_dictionaries(session, active_only=False)

        assert target not in {item.code for item in for_forms.project_types}
        assert target in {item.code for item in for_display.project_types}

    async def test_entries_come_in_configured_order(self, session: AsyncSession) -> None:
        """Порядок задаёт помощник, а не база: без сортировки он был бы случайным."""
        loaded = await service.load_dictionaries(session)

        for entries in (loaded.project_statuses, loaded.project_types, loaded.regions):
            orders = [item.sort_order for item in entries]
            assert orders == sorted(orders)

    async def test_missing_setting_falls_back_to_default(self, session: AsyncSession) -> None:
        """Незаполненный параметр не должен ронять систему."""
        await session.execute(delete(Setting).where(Setting.key == SettingKey.BURN_DAYS))

        value = await service.get_setting(session, SettingKey.BURN_DAYS, default=7)

        assert value == 7


class TestApi:
    async def test_dictionaries_come_in_all_three_scripts(self, assistant_api: AsyncClient) -> None:
        """Ответ содержит все три письменности сразу: язык меняется без нового запроса."""
        response = await assistant_api.get("/api/v1/dictionaries")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "project_types",
            "task_types",
            "directions",
            "regions",
            "project_statuses",
            "task_statuses",
        }
        assert len(body["project_types"]) == 10

        first = body["project_types"][0]
        assert set(first["name"]) == {"ru", "uz_cyrl", "uz_latn"}
        assert all(value.strip() for value in first["name"].values())

    async def test_dictionaries_carry_flags_needed_by_the_interface(
        self, assistant_api: AsyncClient
    ) -> None:
        body = (await assistant_api.get("/api/v1/dictionaries")).json()

        on_hold = next(item for item in body["project_statuses"] if item["code"] == "on_hold")
        assert on_hold["color"]
        assert on_hold["is_terminal"] is False
        assert on_hold["requires_reason"] is True

    async def test_leader_reads_dictionaries_too(self, leader_api: AsyncClient) -> None:
        """Чтение открыто обоим: роль подписывает действие, а не прячет данные (инвариант 13)."""
        response = await leader_api.get("/api/v1/dictionaries")

        assert response.status_code == 200

    async def test_milestone_template_of_a_type(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project_type = await session.scalar(select(ProjectTypeRef).limit(1))
        assert project_type is not None

        response = await assistant_api.get(f"/api/v1/project-types/{project_type.id}/milestones")

        assert response.status_code == 200
        steps = response.json()
        assert steps
        assert [step["sort_order"] for step in steps] == sorted(
            step["sort_order"] for step in steps
        )

    async def test_settings_are_readable(self, assistant_api: AsyncClient) -> None:
        body = (await assistant_api.get("/api/v1/settings")).json()

        assert body[SettingKey.BURN_DAYS] == 7
        assert body[SettingKey.QUIET_DAYS] == 14
        assert body[SettingKey.SUMMARY_AT] == "08:30"

    async def test_center_is_found_by_the_agency_filter(self, assistant_api: AsyncClient) -> None:
        """Срез «что держит Центр» начинается с этого фильтра (ТЗ 5)."""
        response = await assistant_api.get(
            "/api/v1/organizations", params={"founded_by_agency": "true"}
        )

        assert response.status_code == 200
        assert [item["name"] for item in response.json()] == [seed_module.CENTER_NAME]
