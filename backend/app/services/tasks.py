"""Задачи — сборка раздела и правки, которые делает его экран (ТЗ 2, 3.2, блок 1).

Форма — договор экрана `frontend/src/sections/tasks/model.ts`, утверждённого заказчиком
27.09.2026 на вымышленных данных той же формы (CLAUDE.md, цикл блока «экран → API»).

**Числа — из `app.services.metrics`, и больше ниоткуда** (инвариант 2): ступень и
отклонение — строки той же лестницы, что у Пульта; группа по сроку, переносы и «кто
перегружен» — функции того же сервиса.

Разбор строки (`parse`) ничего не пишет: он только предлагает тип, срок и ответственного,
а решает человек (ТЗ 7, инвариант 6). Каждая правка приходит с версией, которую видел
человек (инвариант 15).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import Attention, Ladder, Row
from app.domain.capture import ParsedLine, parse_line
from app.domain.checklists import clean_item
from app.domain.clock import local_date
from app.domain.decisions import DecisionTarget
from app.domain.dictionaries import TaskStatus, localized_name
from app.domain.errors import NotFoundError, RuleViolationError, check_version
from app.domain.projects import clean_description, validate_horizon
from app.domain.tasks import (
    ALLOWED_TRANSITIONS,
    Horizon,
    due_moment,
    validate_title,
    validate_transition,
)
from app.repos import projects as project_model
from app.repos import pult as pult_model
from app.repos import tasks as read_model
from app.repos.models import Task, TaskChecklistItem, User
from app.repos.projects import Names
from app.repos.tasks import TaskRow
from app.services import metrics
from app.services.codes import add_with_code, next_code

TASK_CODE_PREFIX = "TSK"
TASK_CODE_DIGITS = 4

HORIZON_ORDER = list(Horizon)


@dataclass(frozen=True, slots=True)
class PersonRef:
    id: uuid.UUID
    name: str


@dataclass(frozen=True, slots=True)
class CardView:
    id: uuid.UUID
    code: str
    title: str
    type: tuple[str, str] | None
    status: str
    assignee: PersonRef | None
    due_on: date | None
    original_due_on: date | None
    moves: int
    horizon: Horizon
    step: Attention | None
    deviation: int
    project: tuple[uuid.UUID, str, str] | None
    ijro: tuple[uuid.UUID, str] | None
    checklist_done: int
    checklist_total: int
    completed_on: date | None
    version: int
    is_request: bool


@dataclass(frozen=True, slots=True)
class LoadView:
    person: PersonRef
    overdue: int
    burning: int
    open: int


@dataclass(frozen=True, slots=True)
class TasksView:
    as_of: datetime
    items: list[CardView]
    types: list[tuple[str, str]]
    people: list[PersonRef]
    projects: list[tuple[uuid.UUID, str, str]]
    load: list[LoadView]
    is_demo: bool


@dataclass(frozen=True, slots=True)
class ItemView:
    id: uuid.UUID
    text: str
    is_done: bool
    version: int


@dataclass(frozen=True, slots=True)
class DetailView:
    card: CardView
    description: str | None
    items: list[ItemView]
    created_on: date
    question: tuple[str, date] | None
    transitions: list[TaskStatus]


@dataclass(frozen=True, slots=True)
class NewTask:
    title: str
    type_code: str | None
    due_on: date | None
    assignee_id: uuid.UUID | None
    project_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class TaskEdit:
    title: str
    type_code: str | None
    due_on: date | None
    assignee_id: uuid.UUID | None
    project_id: uuid.UUID | None
    description: str | None
    version: int


# --------------------------------------------------------------------------------------
# Чтение
# --------------------------------------------------------------------------------------


def _name(names: Names | None, locale: str) -> str | None:
    if names is None:
        return None
    return localized_name(locale, ru=names.ru, uz_cyrl=names.uz_cyrl, uz_latn=names.uz_latn)


def _open_in_ladder(row: TaskRow) -> bool:
    """Стоит ли задача в лестнице: незакрыта и её проект не закрыт (`repos.attention`)."""
    if TaskStatus(row.status).is_terminal:
        return False
    return row.project_status is None or row.project_status not in read_model.PROJECT_TERMINAL


def _card(
    row: TaskRow, *, steps: dict[uuid.UUID, Row], today: date, zone: ZoneInfo, locale: str
) -> CardView:
    status = TaskStatus(row.status)
    due_on = local_date(row.due_at, zone) if row.due_at else None
    found = steps.get(row.id)
    return CardView(
        id=row.id,
        code=row.code,
        title=row.title,
        type=(row.type_code, _name(row.type_names, locale) or row.type_code)
        if row.type_code
        else None,
        status=row.status,
        assignee=PersonRef(id=row.assignee_id, name=row.assignee_name)
        if row.assignee_id and row.assignee_name
        else None,
        due_on=due_on,
        original_due_on=local_date(row.original_due_at, zone) if row.original_due_at else None,
        moves=metrics.moves_count(row.due_changes, zone=zone),
        horizon=metrics.horizon(status=status, due_on=due_on, today=today),
        step=found.attention if found else None,
        deviation=found.deviation if found else 0,
        project=(row.project_id, row.project_code or "", row.project_title or "")
        if row.project_id
        else None,
        ijro=(row.ijro_id, row.ijro_code or "") if row.ijro_id else None,
        checklist_done=row.checklist_done,
        checklist_total=row.checklist_total,
        completed_on=local_date(row.completed_at, zone) if row.completed_at else None,
        version=row.version,
        is_request=row.is_request,
    )


def _ordered(cards: list[CardView]) -> list[CardView]:
    """Порядок раздела — группа по сроку, внутри по сроку; закрытые — свежие первыми.

    Задача без срока внутри своей группы идёт по названию: срок, которого нет, не ближе
    остальных. Закрытые — отдельным хвостом, последние закрытые сверху: их открывают,
    чтобы проверить только что сделанное.
    """
    open_cards = sorted(
        (card for card in cards if card.horizon is not Horizon.CLOSED),
        key=lambda card: (HORIZON_ORDER.index(card.horizon), card.due_on or date.max, card.title),
    )
    closed = sorted(
        (card for card in cards if card.horizon is Horizon.CLOSED),
        key=lambda card: card.completed_on or date.min,
        reverse=True,
    )
    return open_cards + closed


async def _steps(
    session: AsyncSession, *, today: date, zone: ZoneInfo
) -> tuple[dict[uuid.UUID, Row], Ladder]:
    ladder = await metrics.ladder(session, today=today, zone=zone)
    return {row.entity_id: row for row in ladder.rows if row.section == "tasks"}, ladder


async def load(
    session: AsyncSession, *, now: datetime, zone: ZoneInfo, locale: str, is_demo: bool
) -> TasksView:
    """Весь раздел одним запросом: задачи, «кто перегружен», справочники формы."""
    today = local_date(now, zone)
    steps, ladder = await _steps(session, today=today, zone=zone)
    rows = await read_model.tasks(session)
    people = await project_model.people(session)
    names = dict(people)

    cards = [_card(row, steps=steps, today=today, zone=zone, locale=locale) for row in rows]
    load_rows = metrics.task_load(
        ladder, [(row.id, row.assignee_id) for row in rows if _open_in_ladder(row)]
    )
    return TasksView(
        as_of=now,
        items=_ordered(cards),
        types=[
            (code, _name(kind, locale) or code)
            for code, kind in await read_model.task_types(session)
        ],
        people=[PersonRef(id=person_id, name=name) for person_id, name in people],
        projects=await read_model.project_refs(session),
        load=[
            LoadView(
                person=PersonRef(id=item.person_id, name=names.get(item.person_id, "")),
                overdue=item.overdue,
                burning=item.burning,
                open=item.open,
            )
            for item in load_rows
            if item.person_id in names
        ],
        is_demo=is_demo,
    )


async def _row(session: AsyncSession, task_id: uuid.UUID) -> TaskRow:
    rows = await read_model.tasks(session, ids=[task_id])
    if not rows:
        raise NotFoundError("Задача не найдена: её могли удалить")
    return rows[0]


async def detail(
    session: AsyncSession, *, task_id: uuid.UUID, now: datetime, zone: ZoneInfo, locale: str
) -> DetailView:
    """Карточка задачи: чек-лист, вопрос руководителю, разрешённые переходы."""
    row = await _row(session, task_id)
    today = local_date(now, zone)
    steps, _ = await _steps(session, today=today, zone=zone)
    target = (DecisionTarget.TASK.value, task_id)
    question = (await pult_model.open_questions(session, [target])).get(target)
    return DetailView(
        card=_card(row, steps=steps, today=today, zone=zone, locale=locale),
        description=row.description,
        items=[
            ItemView(id=item.id, text=item.text, is_done=item.is_done, version=item.version)
            for item in await read_model.checklist(session, task_id)
        ],
        created_on=local_date(row.created_at, zone),
        question=(question.text, local_date(question.created_at, zone)) if question else None,
        # Порядок — порядок статусов, а не множества: кнопки не должны прыгать.
        transitions=[
            status for status in TaskStatus if status in ALLOWED_TRANSITIONS[TaskStatus(row.status)]
        ],
    )


async def parse(session: AsyncSession, *, text: str, now: datetime, zone: ZoneInfo) -> ParsedLine:
    """Разбор строки (ТЗ 7) — по действующим людям и типам. Ничего не пишет."""
    people = await project_model.people(session)
    types = await read_model.task_types(session)
    return parse_line(
        text,
        today=local_date(now, zone),
        people=people,
        type_codes={code for code, _ in types},
    )


# --------------------------------------------------------------------------------------
# Запись
# --------------------------------------------------------------------------------------


async def _type_id(
    session: AsyncSession, code: str | None, *, current: uuid.UUID | None
) -> uuid.UUID | None:
    """Тип по коду. Выключенный тип у старой задачи остаётся своим, но заново не выбирается."""
    if not code:
        return None
    found = await read_model.task_type_id(session, code)
    if found is not None:
        return found
    if current is not None and await read_model.task_type_code(session, current) == code:
        return current
    raise RuleViolationError("Такого типа задачи нет среди действующих", detail=code)


async def _check_project(session: AsyncSession, project_id: uuid.UUID | None) -> None:
    if project_id is None:
        return
    is_open = await read_model.project_is_open(session, project_id)
    if is_open is None:
        raise NotFoundError("Проект не найден: его могли удалить")
    if not is_open:
        raise RuleViolationError("Проект завершён или отменён — новая работа в него не входит")


async def _check_assignee(session: AsyncSession, person_id: uuid.UUID | None) -> None:
    if person_id is not None and not await project_model.person_is_active(session, person_id):
        raise NotFoundError("Ответственный не найден среди действующих сотрудников")


async def create(
    session: AsyncSession, *, user: User, data: NewTask, now: datetime, zone: ZoneInfo
) -> uuid.UUID:
    """Новая задача — обязательно одно название (ТЗ 7). Статус — «новая».

    Исходный срок равен сроку: переносов у новой задачи нет. `user` не записывается в
    задачу — автора и время помнит журнал (`app.services.audit`).
    """
    del user
    title = validate_title(data.title)
    type_id = await _type_id(session, data.type_code, current=None)
    await _check_assignee(session, data.assignee_id)
    await _check_project(session, data.project_id)
    due_at = None
    if data.due_on is not None:
        validate_horizon(data.due_on)
        due_at = due_moment(data.due_on, zone)

    task = Task(
        title=title,
        task_type_id=type_id,
        project_id=data.project_id,
        assignee_person_id=data.assignee_id,
        status=TaskStatus.NEW.value,
        due_at=due_at,
        original_due_at=due_at,
    )
    today = local_date(now, zone)
    await add_with_code(
        session,
        task,
        assign=lambda: next_code(
            session, column=Task.code, prefix=TASK_CODE_PREFIX, digits=TASK_CODE_DIGITS, today=today
        ),
    )
    return task.id


async def _task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFoundError("Задача не найдена: её могли удалить")
    return task


async def edit(
    session: AsyncSession, *, task_id: uuid.UUID, data: TaskEdit, zone: ZoneInfo
) -> None:
    """Сведения задачи. Ответственный и проект проверяются, только если их сменили.

    Исходный срок ведёт система: он появляется вместе с первым назначенным сроком и больше
    не меняется (`Task.original_due_at`). Перенос позже журнал запомнит как перенос.
    """
    task = await _task(session, task_id)
    check_version(expected=data.version, actual=task.version)

    title = validate_title(data.title)
    type_id = await _type_id(session, data.type_code, current=task.task_type_id)
    if data.assignee_id != task.assignee_person_id:
        await _check_assignee(session, data.assignee_id)
    if data.project_id != task.project_id:
        await _check_project(session, data.project_id)

    due_at = task.due_at
    if data.due_on is None:
        due_at = None
    elif task.due_at is None or local_date(task.due_at, zone) != data.due_on:
        validate_horizon(data.due_on)
        due_at = due_moment(data.due_on, zone)

    task.title = title
    task.task_type_id = type_id
    task.assignee_person_id = data.assignee_id
    task.project_id = data.project_id
    task.due_at = due_at
    if task.original_due_at is None and due_at is not None:
        task.original_due_at = due_at
    task.description = clean_description(data.description)
    await session.flush()


async def set_status(
    session: AsyncSession, *, task_id: uuid.UUID, status: TaskStatus, version: int, now: datetime
) -> None:
    """Статус — по графу переходов (`domain/tasks`). Отметки времени ставит система.

    Начало работы — при первом переходе «в работу»; закрытие — при «готова» и «отменена»;
    переоткрытие снимает отметку закрытия: работа, которую снова делают, не закрыта.
    """
    task = await _task(session, task_id)
    check_version(expected=version, actual=task.version)
    current = TaskStatus(task.status)
    validate_transition(current=current, target=status)
    if status is current:
        return
    task.status = status.value
    if status is TaskStatus.IN_PROGRESS and task.started_at is None:
        task.started_at = now
    if status.is_terminal:
        task.completed_at = now
    elif current.is_terminal:
        task.completed_at = None
    await session.flush()


async def add_item(session: AsyncSession, *, task_id: uuid.UUID, text: str) -> uuid.UUID:
    """Новый пункт чек-листа — в конец."""
    await _task(session, task_id)
    item = TaskChecklistItem(
        task_id=task_id,
        text=clean_item(text),
        sort_order=await read_model.next_sort_order(session, task_id),
    )
    session.add(item)
    await session.flush()
    return item.id


async def _item(session: AsyncSession, task_id: uuid.UUID, item_id: uuid.UUID) -> TaskChecklistItem:
    found = await read_model.item(session, task_id, item_id)
    if found is None:
        raise NotFoundError("Пункт чек-листа не найден: его могли убрать")
    return found


async def toggle_item(
    session: AsyncSession, *, task_id: uuid.UUID, item_id: uuid.UUID, done: bool, version: int
) -> None:
    """Отметка пункта — одно касание; она же признак жизни задачи (`repos.attention`)."""
    item = await _item(session, task_id, item_id)
    check_version(expected=version, actual=item.version)
    item.is_done = done
    await session.flush()


async def remove_item(
    session: AsyncSession, *, task_id: uuid.UUID, item_id: uuid.UUID, version: int
) -> None:
    item = await _item(session, task_id, item_id)
    check_version(expected=version, actual=item.version)
    await session.delete(item)
    await session.flush()
