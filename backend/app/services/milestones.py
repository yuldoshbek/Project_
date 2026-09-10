"""Вехи проекта: сценарии использования."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import NotFoundError, RuleViolationError
from app.domain.milestones import MilestoneState, MilestoneStatus, effective_status
from app.repos.models import Milestone
from app.services.projects import get as get_project

_UNSET: Any = object()


@dataclass(frozen=True, slots=True)
class MilestoneView:
    milestone: Milestone
    status: MilestoneStatus


def view(milestone: Milestone, *, today: date) -> MilestoneView:
    return MilestoneView(
        milestone=milestone,
        status=effective_status(
            state=MilestoneState(milestone.state), due_on=milestone.due_on, today=today
        ),
    )


@dataclass(slots=True)
class MilestoneDraft:
    title: str
    due_on: date
    description: str | None = None
    state: MilestoneState = MilestoneState.PLANNED


@dataclass(slots=True)
class MilestonePatch:
    title: Any = _UNSET
    description: Any = _UNSET
    due_on: Any = _UNSET
    state: Any = _UNSET

    def assigned(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__slots__
            if getattr(self, name) is not _UNSET
        }


async def list_for_project(
    session: AsyncSession, project_id: uuid.UUID, *, today: date
) -> list[MilestoneView]:
    """Вехи проекта в заданном человеком порядке.

    Порядок задаёт человек, а не дата: согласование идёт раньше подписания, даже если
    сроки у них одинаковые. При равном порядке добивка по сроку — чтобы список не
    перетасовывался между запросами.

    Проект проверяется на существование: вехи несуществующего проекта — это `404`, а не
    пустой список. Пустой список означал бы «вех нет», и опечатка в адресе выглядела бы
    как только что удалённый кем-то раздел.
    """
    await get_project(session, project_id)

    rows = await session.scalars(
        select(Milestone)
        .where(Milestone.project_id == project_id)
        .order_by(Milestone.sort_order, Milestone.due_on)
    )
    return [view(item, today=today) for item in rows]


async def get(session: AsyncSession, milestone_id: uuid.UUID) -> Milestone:
    milestone = await session.get(Milestone, milestone_id)
    if milestone is None:
        raise NotFoundError("Веха не найдена")
    return milestone


async def create(session: AsyncSession, project_id: uuid.UUID, draft: MilestoneDraft) -> Milestone:
    await get_project(session, project_id)

    last = await session.scalar(
        select(func.max(Milestone.sort_order)).where(Milestone.project_id == project_id)
    )
    milestone = Milestone(
        project_id=project_id,
        title=draft.title.strip(),
        description=draft.description,
        due_on=draft.due_on,
        state=draft.state.value,
        sort_order=(last or 0) + 1,
    )
    session.add(milestone)
    await session.flush()
    return milestone


async def update(
    session: AsyncSession, milestone_id: uuid.UUID, patch: MilestonePatch
) -> Milestone:
    milestone = await get(session, milestone_id)
    for name, value in patch.assigned().items():
        setattr(milestone, name, value.value if isinstance(value, Enum) else value)
    await session.flush()
    return milestone


async def delete(session: AsyncSession, milestone_id: uuid.UUID) -> None:
    milestone = await get(session, milestone_id)
    await session.delete(milestone)
    await session.flush()


async def reorder(
    session: AsyncSession, project_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> list[Milestone]:
    """Переупорядочивание списком целиком, а не сдвигом по одной.

    Приходит весь порядок: частичная перестановка «подними эту на одну вверх» оставляет
    список в неопределённом состоянии, если два запроса пришли подряд.

    Присланный список обязан совпадать с имеющимся по составу. Иначе перетаскивание,
    начатое до того, как веху удалили, тихо оставило бы часть вех с прежним порядком — и
    список после перезагрузки выглядел бы иначе, чем только что на экране.
    """
    existing = {
        item.id: item
        for item in await session.scalars(
            select(Milestone).where(Milestone.project_id == project_id)
        )
    }
    if len(ordered_ids) != len(existing) or set(ordered_ids) != set(existing):
        raise RuleViolationError(
            "Присланный порядок не совпадает с составом вех проекта",
            detail="список изменился: обновите карточку и повторите",
        )

    for position, milestone_id in enumerate(ordered_ids, start=1):
        existing[milestone_id].sort_order = position

    await session.flush()
    return [existing[milestone_id] for milestone_id in ordered_ids]
