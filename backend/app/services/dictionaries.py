"""Чтение справочников.

Изменение справочников — тикет ORB-035; здесь только чтение.

Все справочники отдаются одним ответом. Форма создания проекта нуждается сразу в
направлениях, приоритетах и статусах: пять отдельных запросов при открытии формы — это
пять ожиданий там, где норматив ТЗ 10.5 отводит на всё создание две минуты.
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
    PriorityRef,
    ProjectStatusRef,
    Setting,
    TaskStatusRef,
)


@dataclass(frozen=True, slots=True)
class Dictionaries:
    directions: list[Direction]
    project_statuses: list[ProjectStatusRef]
    task_statuses: list[TaskStatusRef]
    priorities: list[PriorityRef]


def _ordered(model: Any, *, active_only: bool) -> Select[Any]:
    statement = select(model).order_by(model.sort_order, model.name_ru)
    if active_only:
        statement = statement.where(model.is_active.is_(True))
    return statement


async def load_dictionaries(session: AsyncSession, *, active_only: bool = True) -> Dictionaries:
    """Все справочники одним обращением.

    `active_only` отделяет формы создания от просмотра существующих записей: в форме
    отключённое значение выбирать нельзя, а в старом проекте оно должно отображаться —
    иначе исчезнет направление, по которому проект когда-то завели (критерий ORB-010).
    """
    return Dictionaries(
        directions=list(await session.scalars(_ordered(Direction, active_only=active_only))),
        project_statuses=list(
            await session.scalars(_ordered(ProjectStatusRef, active_only=active_only))
        ),
        task_statuses=list(await session.scalars(_ordered(TaskStatusRef, active_only=active_only))),
        priorities=list(await session.scalars(_ordered(PriorityRef, active_only=active_only))),
    )


async def list_organizations(
    session: AsyncSession,
    *,
    active_only: bool = True,
    search: str | None = None,
) -> list[Organization]:
    """Организации-партнёры.

    Отдельно от остальных справочников: их число растёт, и класть их в общий ответ
    значило бы утяжелять открытие каждой формы. Полноценный поиск по названию —
    ORB-033; здесь простое совпадение по подстроке.
    """
    statement = select(Organization).order_by(Organization.name)
    if active_only:
        statement = statement.where(Organization.is_active.is_(True))
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(Organization.name.ilike(pattern))
    return list(await session.scalars(statement))


async def load_settings(session: AsyncSession) -> dict[str, Any]:
    """Настраиваемые параметры в виде «ключ — значение»."""
    rows = await session.scalars(select(Setting).order_by(Setting.key))
    return {row.key: row.value for row in rows}


async def get_setting(session: AsyncSession, key: SettingKey, default: Any = None) -> Any:
    """Один параметр.

    Значение по умолчанию нужно на случай, когда параметр ещё не заведён сидами: система
    должна работать, а не падать из-за отсутствующей строки в справочнике.
    """
    value = await session.scalar(select(Setting.value).where(Setting.key == str(key)))
    return default if value is None else value
