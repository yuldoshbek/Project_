"""Чтение справочников (ТЗ 3.9).

Все справочники отдаются одним ответом. Форма создания проекта нуждается сразу в типах,
направлениях, регионах и статусах: пять отдельных запросов при открытии формы — это пять
ожиданий там, где вся стоимость ввода должна укладываться в минуту (ТЗ 1).

Организации отдаются отдельно: их число растёт, и класть их в общий ответ значило бы
утяжелять открытие каждой формы.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dictionaries import SettingKey
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
)


@dataclass(frozen=True, slots=True)
class Dictionaries:
    project_types: list[ProjectTypeRef]
    task_types: list[TaskTypeRef]
    directions: list[Direction]
    regions: list[Region]
    project_statuses: list[ProjectStatusRef]
    task_statuses: list[TaskStatusRef]


def _ordered(model: Any, *, active_only: bool) -> Select[Any]:
    statement = select(model).order_by(model.sort_order, model.name_ru)
    if active_only:
        statement = statement.where(model.is_active.is_(True))
    return statement


async def load_dictionaries(session: AsyncSession, *, active_only: bool = True) -> Dictionaries:
    """Все справочники одним обращением.

    `active_only` отделяет формы создания от просмотра существующих записей: в форме
    отключённое значение выбирать нельзя, а в старом проекте оно должно отображаться —
    иначе исчезнет тип, по которому проект когда-то завели.
    """
    return Dictionaries(
        project_types=list(
            await session.scalars(_ordered(ProjectTypeRef, active_only=active_only))
        ),
        task_types=list(await session.scalars(_ordered(TaskTypeRef, active_only=active_only))),
        directions=list(await session.scalars(_ordered(Direction, active_only=active_only))),
        regions=list(await session.scalars(_ordered(Region, active_only=active_only))),
        project_statuses=list(
            await session.scalars(_ordered(ProjectStatusRef, active_only=active_only))
        ),
        task_statuses=list(await session.scalars(_ordered(TaskStatusRef, active_only=active_only))),
    )


async def milestone_template(
    session: AsyncSession, project_type_id: Any
) -> list[ProjectTypeMilestone]:
    """Шаблон вех выбранного типа проекта.

    Ради этого типы и заводятся: помощник выбирает «нормативный акт» и получает вехи
    готовыми, а не вспоминает их каждый раз (ТЗ 1, стоимость ввода).
    """
    return list(
        await session.scalars(
            select(ProjectTypeMilestone)
            .where(ProjectTypeMilestone.project_type_id == project_type_id)
            .order_by(ProjectTypeMilestone.sort_order, ProjectTypeMilestone.offset_days)
        )
    )


async def list_organizations(
    session: AsyncSession,
    *,
    active_only: bool = True,
    search: str | None = None,
    founded_by_agency: bool | None = None,
) -> list[Organization]:
    """Организации. `founded_by_agency` отбирает Центр — срез «что держит Центр» (ТЗ 5)."""
    statement = select(Organization).order_by(Organization.name)
    if active_only:
        statement = statement.where(Organization.is_active.is_(True))
    if founded_by_agency is not None:
        statement = statement.where(Organization.is_founded_by_agency.is_(founded_by_agency))
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            Organization.name.ilike(pattern) | Organization.short_name.ilike(pattern)
        )
    return list(await session.scalars(statement))


async def load_settings(session: AsyncSession) -> dict[str, Any]:
    """Пороги сигналов в виде «ключ — значение»."""
    rows = await session.scalars(select(Setting).order_by(Setting.key))
    return {row.key: row.value for row in rows}


async def get_setting(session: AsyncSession, key: SettingKey, default: Any = None) -> Any:
    """Один порог.

    Значение по умолчанию нужно на случай, когда порог ещё не заведён: система должна
    работать, а не падать из-за отсутствующей строки в справочнике.
    """
    value = await session.scalar(select(Setting.value).where(Setting.key == str(key)))
    return default if value is None else value
