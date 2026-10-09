"""Сценарии раздела «Идеи и карты» (ТЗ 3.6, 5).

Решение руководителя по идее и превращение узла карты в проект или задачу заводят
настоящую запись тем же сценарием, что и разделы (`services.projects.create`,
`services.tasks.create`), в одной транзакции со ссылкой на неё: идея без ссылки на выросший
проект или проект без идеи — половина решения.

Ступень узла в режиме «Структура» — строка той же лестницы, что на Пульте (инвариант 2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import ideas as rules
from app.domain.attention import Attention
from app.domain.clock import local_date
from app.domain.dictionaries import localized_name
from app.domain.errors import (
    STALE_VERSION_MESSAGE,
    NotFoundError,
    RuleViolationError,
    StaleVersionError,
    check_version,
)
from app.domain.files import FileOwner
from app.domain.ideas import IdeaStep, MapMode, Outcome
from app.repos import ideas as read_model
from app.repos import projects as project_model
from app.repos.ideas import IdeaRow, MapRow, NodeRow
from app.repos.models import Idea, IdeaMap, MapNode, User
from app.services import files, metrics, projects, tasks


@dataclass(frozen=True, slots=True)
class PhotoRef:
    id: uuid.UUID
    name: str


@dataclass(frozen=True, slots=True)
class IdeaView:
    row: IdeaRow
    waiting_days: int
    """Сколько дней ждёт руководителя — из ответа `metrics.ideas_awaiting` (V46); у не
    отправленной — 0."""
    photos: list[PhotoRef]
    """Фото, снятые вместе с идеей в Захвате (V18): строка идеи и есть её карточка, и фото
    приходят вместе со списком — одним запросом на все идеи, а не запросом на строку."""


@dataclass(frozen=True, slots=True)
class TypeOption:
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class IdeasView:
    as_of: datetime
    questions: list[rules.Answer]
    items: list[IdeaView]
    maps: list[MapRow]
    project_types: list[TypeOption]
    is_demo: bool


@dataclass(frozen=True, slots=True)
class NodeView:
    row: NodeRow
    step: Attention | None
    deviation: int


@dataclass(frozen=True, slots=True)
class MapView:
    map: MapRow
    nodes: list[NodeView]
    project_types: list[TypeOption]


async def _types(session: AsyncSession, locale: str) -> list[TypeOption]:
    return [
        TypeOption(
            code=kind.code,
            name=localized_name(
                locale, ru=kind.names.ru, uz_cyrl=kind.names.uz_cyrl, uz_latn=kind.names.uz_latn
            )
            or kind.names.ru,
        )
        for kind in await project_model.project_types(session)
    ]


# --------------------------------------------------------------------------------------
# Идеи
# --------------------------------------------------------------------------------------


async def load(
    session: AsyncSession, *, now: datetime, zone: ZoneInfo, locale: str, is_demo: bool
) -> IdeasView:
    today = local_date(now, zone)
    rows = await read_model.ideas(session)
    waiting = [
        rules.Waiting(id=row.id, since=local_date(row.review_at, zone), sent_at=row.review_at)
        for row in rows
        if row.step == IdeaStep.REVIEW.value and row.review_at is not None
    ]
    answer = metrics.ideas_awaiting(waiting, today=today)
    photos = await files.photos_by_owner(
        session, owner=FileOwner.IDEA, owner_ids=[row.id for row in rows]
    )
    return IdeasView(
        as_of=now,
        questions=[answer],
        items=[
            IdeaView(
                row=row,
                waiting_days=answer.days.get(row.id, 0),
                photos=[PhotoRef(id=photo.id, name=photo.name) for photo in photos.get(row.id, [])],
            )
            for row in rows
        ],
        maps=await read_model.maps(session),
        project_types=await _types(session, locale),
        is_demo=is_demo,
    )


async def _idea(session: AsyncSession, idea_id: uuid.UUID) -> Idea:
    idea = await session.get(Idea, idea_id)
    if idea is None:
        raise NotFoundError("Идея не найдена")
    return idea


async def create_idea(session: AsyncSession, *, user: User, text: str) -> uuid.UUID:
    """Новая идея — набросок; пишут оба (ТЗ 6: руководитель «записать идею»)."""
    idea = Idea(text=rules.clean_text(text), author_id=user.id, step=IdeaStep.DRAFT.value)
    session.add(idea)
    await session.flush()
    return idea.id


async def edit_idea(session: AsyncSession, *, idea_id: uuid.UUID, text: str, version: int) -> None:
    idea = await _idea(session, idea_id)
    check_version(expected=version, actual=idea.version)
    cleaned = rules.clean_text(text)
    if idea.text != cleaned:
        idea.text = cleaned


async def to_review(
    session: AsyncSession, *, idea_id: uuid.UUID, version: int, now: datetime
) -> None:
    """На рассмотрение: с этой минуты идея ждёт руководителя (V46); отложенная — снова (V47)."""
    idea = await _idea(session, idea_id)
    check_version(expected=version, actual=idea.version)
    rules.check_to_review(IdeaStep(idea.step), Outcome(idea.outcome) if idea.outcome else None)
    idea.step = IdeaStep.REVIEW.value
    idea.outcome = None
    idea.decided_at = None
    idea.review_at = now


async def _create_work(
    session: AsyncSession,
    *,
    user: User,
    kind: Outcome,
    title: str,
    type_code: str | None,
    now: datetime,
    zone: ZoneInfo,
) -> uuid.UUID:
    """Проект или задача из идеи или узла — тем же сценарием, что в разделе.

    Название обрезается по слову до предела раздела: идея в тысячу знаков — замысел, а
    название проекта — строка списка. Полный текст остаётся в идее и в узле.
    """
    if kind is Outcome.PROJECT:
        if not type_code:
            raise RuleViolationError("Для проекта нужен тип")
        return await projects.create(
            session,
            user=user,
            data=projects.NewProject(
                title=_title(title),
                type_code=type_code,
                started_on=local_date(now, zone),
                due_on=None,
                responsible_id=None,
                parent_id=None,
                is_multiyear=False,
            ),
            today=local_date(now, zone),
        )
    return await tasks.create(
        session,
        user=user,
        data=tasks.NewTask(
            title=_title(title), type_code=None, due_on=None, assignee_id=None, project_id=None
        ),
        now=now,
        zone=zone,
    )


TITLE_LIMIT = 300
"""Название проекта и задачи из идеи — не длиннее строки списка разделов."""


def _title(text: str) -> str:
    if len(text) <= TITLE_LIMIT:
        return text
    return text[: TITLE_LIMIT - 1].rsplit(" ", 1)[0] + "…"


async def decide(
    session: AsyncSession,
    *,
    user: User,
    idea_id: uuid.UUID,
    outcome: Outcome,
    type_code: str | None,
    version: int,
    now: datetime,
    zone: ZoneInfo,
) -> uuid.UUID | None:
    """Решение руководителя: проект, задача или «отложено» — одним действием (критерий 1)."""
    idea = await _idea(session, idea_id)
    check_version(expected=version, actual=idea.version)
    rules.check_decision(IdeaStep(idea.step), Outcome(idea.outcome) if idea.outcome else None)
    created: uuid.UUID | None = None
    if outcome is not Outcome.POSTPONED:
        created = await _create_work(
            session,
            user=user,
            kind=outcome,
            title=idea.text,
            type_code=type_code,
            now=now,
            zone=zone,
        )
    idea.step = IdeaStep.DECIDED.value
    idea.outcome = outcome.value
    idea.decided_at = now
    idea.project_id = created if outcome is Outcome.PROJECT else None
    idea.task_id = created if outcome is Outcome.TASK else None
    return created


# --------------------------------------------------------------------------------------
# Карты
# --------------------------------------------------------------------------------------


async def _map(session: AsyncSession, map_id: uuid.UUID, *, lock: bool = False) -> IdeaMap:
    found = await session.get(IdeaMap, map_id, with_for_update=lock)
    if found is None:
        raise NotFoundError("Карта не найдена")
    return found


async def _lock_tree(session: AsyncSession, map_id: uuid.UUID) -> None:
    """Правки дерева одной карты — по очереди: строка карты блокируется до конца транзакции.

    Проверка кольца и состав удаляемой ветви читают родителей снимком. Без очереди два
    одновременных переноса (X под Y и Y под X) проходят обе проверки и замыкают кольцо,
    а удаление ветви каскадом базы уносит узел, добавленный в ту же секунду, мимо журнала.
    """
    await _map(session, map_id, lock=True)


async def _node(session: AsyncSession, map_id: uuid.UUID, node_id: uuid.UUID) -> MapNode:
    node = await session.get(MapNode, node_id)
    if node is None or node.map_id != map_id:
        raise NotFoundError("Узел не найден")
    return node


async def card(
    session: AsyncSession, *, map_id: uuid.UUID, now: datetime, zone: ZoneInfo, locale: str
) -> MapView:
    row = await read_model.map_row(session, map_id)
    if row is None:
        raise NotFoundError("Карта не найдена")
    nodes = await read_model.nodes(session, map_id)
    steps: dict[tuple[str, uuid.UUID], tuple[Attention, int]] = {}
    if any(node.link is not None for node in nodes):
        thresholds = await metrics.load_thresholds(session)
        ladder = await metrics.ladder(
            session, today=local_date(now, zone), zone=zone, thresholds=thresholds
        )
        steps = {
            (each.section, each.entity_id): (each.attention, each.deviation) for each in ladder.rows
        }
    section = {"project": "projects", "task": "tasks"}
    views: list[NodeView] = []
    for node in nodes:
        found = steps.get((section[node.link.type], node.link.id)) if node.link else None
        views.append(
            NodeView(
                row=node,
                step=found[0] if found else None,
                deviation=found[1] if found else 0,
            )
        )
    return MapView(map=row, nodes=views, project_types=await _types(session, locale))


async def create_map(session: AsyncSession, *, title: str, mode: MapMode) -> uuid.UUID:
    created = IdeaMap(title=rules.clean_title(title), mode=mode.value)
    session.add(created)
    await session.flush()
    return created.id


async def edit_map(
    session: AsyncSession, *, map_id: uuid.UUID, title: str, mode: MapMode, version: int
) -> None:
    found = await _map(session, map_id)
    check_version(expected=version, actual=found.version)
    cleaned = rules.clean_title(title)
    if found.title != cleaned:
        found.title = cleaned
    if found.mode != mode.value:
        found.mode = mode.value


async def add_node(
    session: AsyncSession,
    *,
    map_id: uuid.UUID,
    text: str,
    parent_id: uuid.UUID | None,
    x: int,
    y: int,
) -> uuid.UUID:
    await _lock_tree(session, map_id)
    rules.check_point(x, y)
    rules.check_parent(None, parent_id, await read_model.parents(session, map_id))
    node = MapNode(
        map_id=map_id,
        parent_id=parent_id,
        text=rules.clean_text(text, limit=rules.NODE_TEXT_MAX_LENGTH),
        x=x,
        y=y,
    )
    session.add(node)
    await session.flush()
    return node.id


async def edit_node(
    session: AsyncSession, *, map_id: uuid.UUID, node_id: uuid.UUID, text: str, version: int
) -> None:
    node = await _node(session, map_id, node_id)
    check_version(expected=version, actual=node.version)
    cleaned = rules.clean_text(text, limit=rules.NODE_TEXT_MAX_LENGTH)
    if node.text != cleaned:
        node.text = cleaned


async def move_node(
    session: AsyncSession, *, map_id: uuid.UUID, node_id: uuid.UUID, x: int, y: int, version: int
) -> None:
    node = await _node(session, map_id, node_id)
    check_version(expected=version, actual=node.version)
    rules.check_point(x, y)
    if (node.x, node.y) != (x, y):
        node.x, node.y = x, y


async def set_parent(
    session: AsyncSession,
    *,
    map_id: uuid.UUID,
    node_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    version: int,
) -> None:
    await _lock_tree(session, map_id)
    node = await _node(session, map_id, node_id)
    check_version(expected=version, actual=node.version)
    rules.check_parent(node_id, parent_id, await read_model.parents(session, map_id))
    if node.parent_id != parent_id:
        node.parent_id = parent_id


async def delete_node(
    session: AsyncSession,
    *,
    map_id: uuid.UUID,
    node_id: uuid.UUID,
    version: int,
    branch: str,
) -> int:
    """Узел уходит вместе с ветвью (`rules.subtree`); проекты и задачи остаются — карта
    только ссылается на них.

    `branch` — отпечаток ветви, которую видел человек (`rules.branch_stamp`). Версия корня не
    меняется, когда под него добавляют, переносят или правят узлы, поэтому одной версии
    мало: удаление по устаревшей картине молча унесло бы чужую правку (инвариант 15).
    """
    await _lock_tree(session, map_id)
    node = await _node(session, map_id, node_id)
    check_version(expected=version, actual=node.version)
    ids = rules.subtree(node_id, await read_model.parents(session, map_id))
    # Строки ветви уже под блокировкой карты (`_lock_tree`): между сверкой и удалением их
    # никто не поменяет.
    gone = [found for each in ids if (found := await session.get(MapNode, each)) is not None]
    if rules.branch_stamp((each.id, each.version) for each in gone) != branch:
        raise StaleVersionError(STALE_VERSION_MESSAGE)
    # Удаление по одной строке — чтобы каждое попало в журнал (инвариант 5).
    for found in gone:
        await session.delete(found)
    await session.flush()
    return len(gone)


async def convert_node(
    session: AsyncSession,
    *,
    user: User,
    map_id: uuid.UUID,
    node_id: uuid.UUID,
    kind: Outcome,
    type_code: str | None,
    version: int,
    now: datetime,
    zone: ZoneInfo,
) -> uuid.UUID:
    """Узел → проект или задача одним действием (ТЗ 11): запись заводится, узел — ссылается."""
    if kind is Outcome.POSTPONED:
        raise RuleViolationError("Узел превращается в проект или задачу")
    node = await _node(session, map_id, node_id)
    check_version(expected=version, actual=node.version)
    if node.project_id is not None or node.task_id is not None:
        raise RuleViolationError("Узел уже связан с записью")
    created = await _create_work(
        session,
        user=user,
        kind=kind,
        title=node.text,
        type_code=type_code,
        now=now,
        zone=zone,
    )
    if kind is Outcome.PROJECT:
        node.project_id = created
    else:
        node.task_id = created
    return created
