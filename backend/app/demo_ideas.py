"""Вымышленные идеи и карты для демо и превью (инвариант 11).

Идеи — на всех шагах пути: набросок руководителя из Захвата, две на рассмотрении разного
возраста (вопрос «Что ждёт моего „да“?» отвечает старшей), решённая в проект и отложенная.
Карта «Мониторинг сельского хозяйства» — в режиме «Структура»: часть узлов связана с
проектами и задачами демо и показывает их ступень, часть — ещё нет. Вторая карта —
набросок.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ideas import IdeaStep, MapMode, Outcome
from app.repos.models import Idea, IdeaMap, MapNode, Project, Task


@dataclass(frozen=True, slots=True)
class IdeaSpec:
    text: str
    author: str
    days_ago: float
    step: IdeaStep
    review_days_ago: int | None = None
    outcome: Outcome | None = None
    project: str | None = None


IDEAS = (
    IdeaSpec(
        # Та же фраза, что записал руководитель в Захвате (`app.demo.CAPTURES`).
        "Спутниковый мониторинг пастбищ — предложить Минсельхозу пилот на весну",
        "leader",
        26 / 24,
        IdeaStep.DRAFT,
    ),
    IdeaSpec(
        "Открытый каталог снимков для вузов: бесплатный доступ к архиву старше года",
        "assistant",
        14,
        IdeaStep.REVIEW,
        review_days_ago=9,
    ),
    IdeaSpec(
        "Ежемесячная сводка по водным ресурсам для хокимиятов областей",
        "assistant",
        5,
        IdeaStep.REVIEW,
        review_days_ago=3,
    ),
    IdeaSpec(
        "Пилот мониторинга посевов вместе с Минсельхозом",
        "leader",
        60,
        IdeaStep.DECIDED,
        outcome=Outcome.PROJECT,
        project="crops",
    ),
    IdeaSpec(
        "Мобильное приложение для фермеров со снимками их полей",
        "assistant",
        30,
        IdeaStep.DECIDED,
        outcome=Outcome.POSTPONED,
    ),
)


@dataclass(frozen=True, slots=True)
class NodeSpec:
    key: str
    text: str
    x: int
    y: int
    parent: str | None = None
    project: str | None = None
    task: str | None = None


AGRICULTURE = (
    NodeSpec("root", "Мониторинг сельского хозяйства", 430, 270),
    NodeSpec("crops", "Пилот: мониторинг посевов", 180, 130, "root", project="crops"),
    NodeSpec("selection", "Отбор участников пилота", 0, 0, "crops", task="pilot-selection"),
    NodeSpec("drought", "Засуха", 680, 130, "root", project="drought"),
    NodeSpec("note", "Справка по засухе", 860, 0, "drought", task="drought-note"),
    NodeSpec("pasture", "Пастбища", 180, 420, "root"),
    NodeSpec("water", "Водные ресурсы", 680, 420, "root"),
    NodeSpec("reservoirs", "Наполнение водохранилищ", 860, 540, "water"),
)

EDUCATION = (
    NodeSpec("root", "Космическое образование", 400, 240),
    NodeSpec("school", "Кружки в школах", 120, 100, "root"),
    NodeSpec("contest", "Конкурс по обработке снимков", 680, 100, "root"),
    NodeSpec("museum", "Выставка в музее", 400, 420, "root"),
)


async def load(
    session: AsyncSession,
    *,
    now: datetime,
    users: dict[str, uuid.UUID],
    projects: dict[str, Project],
    tasks: dict[str, Task],
) -> int:
    for idea in IDEAS:
        created = now - timedelta(days=idea.days_ago)
        decided = idea.step is IdeaStep.DECIDED
        session.add(
            Idea(
                text=idea.text,
                author_id=users[idea.author],
                step=idea.step.value,
                outcome=idea.outcome.value if idea.outcome else None,
                review_at=(
                    now - timedelta(days=idea.review_days_ago)
                    if idea.review_days_ago is not None
                    else None
                ),
                decided_at=created + timedelta(days=2) if decided else None,
                project_id=projects[idea.project].id if idea.project else None,
                created_at=created,
            )
        )

    for title, mode, specs, age in (
        ("Мониторинг сельского хозяйства", MapMode.STRUCTURE, AGRICULTURE, 12),
        ("Космическое образование", MapMode.SKETCH, EDUCATION, 4),
    ):
        made = now - timedelta(days=age)
        board = IdeaMap(title=title, mode=mode.value, created_at=made)
        session.add(board)
        await session.flush()
        nodes: dict[str, MapNode] = {}
        for order, spec in enumerate(specs):
            node = MapNode(
                map_id=board.id,
                parent_id=nodes[spec.parent].id if spec.parent else None,
                text=spec.text,
                x=spec.x,
                y=spec.y,
                project_id=projects[spec.project].id if spec.project else None,
                task_id=tasks[spec.task].id if spec.task else None,
                # Порядок заведения — порядок контура на телефоне.
                created_at=made + timedelta(minutes=order),
            )
            session.add(node)
            await session.flush()
            nodes[spec.key] = node
    await session.flush()
    return len(IDEAS)
