"""Проекты — сборка раздела и правки, которые делает его экран (ТЗ 5, блок 1).

Форма — договор экрана `frontend/src/sections/projects/model.ts`, утверждённого заказчиком
25.09.2026 на вымышленных данных той же формы (CLAUDE.md, цикл блока «экран → API»).

**Числа — из `app.services.metrics`, и больше ниоткуда** (инвариант 2): ступень и
отклонение — строки той же лестницы, что у Пульта; готовность, отставание, переносы и
свежесть «что мешает» — функции того же сервиса. Здесь к ним добавляется то, что делает
плитку понятной: названия, ответственный, роль Центра, вехи.

**«Что если» ничего не записывает.** Он читает снимок и считает две лестницы
(`metrics.what_if`); правки объектов в нём нет. Записывает новые сроки только
`apply_dates` — отдельное действие помощника, и перенос позже виден в журнале как
перенос.

Каждая правка приходит с версией, которую видел человек (инвариант 15): помощник мог
поменять проект в соседней вкладке, пока руководитель считал «что если», и сохранять
поверх — значит молча стереть чужую правку.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import LADDER, Attention, Ladder, Row
from app.domain.clock import local_date
from app.domain.decisions import DecisionTarget
from app.domain.dictionaries import ProjectStatus, localized_name
from app.domain.errors import ConflictError, NotFoundError, RuleViolationError, check_version
from app.domain.projects import (
    clean_impediment,
    default_due_on,
    template_dates,
    validate_dates,
    validate_horizon,
    validate_nesting,
    validate_program,
    validate_status_reason,
    validate_title,
)
from app.repos import projects as read_model
from app.repos import pult as pult_model
from app.repos.models import Milestone, Project, User
from app.repos.projects import Names, ProjectRow
from app.services import metrics
from app.services.codes import add_with_code, next_code

PROJECT_CODE_PREFIX = "PRJ"
PROJECT_CODE_DIGITS = 3

MAX_CHANGES = 100
"""Сколько сроков можно сдвинуть одним «что если». Больше вех у проекта не бывает, а
запрос на тысячу строк — это уже не расчёт с экрана, а нагрузка."""

STEPS = tuple(step for step in LADDER if not step.is_normal)

# Раздел строки лестницы: проект и его вехи.
PROJECTS = "projects"
MILESTONES = "milestones"

Key = tuple[str, uuid.UUID]


class ChangeKind(StrEnum):
    """Что сдвигает «что если»: срок проекта или срок вехи."""

    PROJECT = "project"
    MILESTONE = "milestone"


@dataclass(frozen=True, slots=True)
class DueChange:
    kind: ChangeKind
    id: uuid.UUID
    due_on: date
    version: int | None = None
    """Версия, которую видел человек, — нужна только записи (`apply_dates`)."""


@dataclass(frozen=True, slots=True)
class NewProject:
    title: str
    type_code: str
    started_on: date
    due_on: date | None
    responsible_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    is_multiyear: bool


# --------------------------------------------------------------------------------------
# Виды — то, что отдаёт API
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PersonRef:
    id: uuid.UUID
    name: str


@dataclass(frozen=True, slots=True)
class ImpedimentView:
    text: str
    updated_on: date
    stale: bool


@dataclass(frozen=True, slots=True)
class MarkView:
    title: str
    due_on: date
    is_passed: bool


@dataclass(frozen=True, slots=True)
class CardView:
    id: uuid.UUID
    code: str
    title: str
    type_code: str
    type_name: str
    status: str
    status_reason: str | None
    parent: tuple[uuid.UUID, str] | None
    is_multiyear: bool
    subprojects: int
    started_on: date
    due_on: date
    original_due_on: date
    moves: int
    responsible: PersonRef | None
    readiness: int
    lag_days: int
    step: Attention | None
    deviation: int
    impediment: ImpedimentView | None
    lead_outside: bool
    center_role: str | None
    next_milestone: MarkView | None
    milestones_passed: int
    milestones_total: int
    tasks_done: int
    tasks_total: int
    marks: list[MarkView]
    version: int


@dataclass(frozen=True, slots=True)
class TypeView:
    code: str
    name: str
    template: list[tuple[str, int]]


@dataclass(frozen=True, slots=True)
class ProjectsView:
    as_of: datetime
    items: list[CardView]
    types: list[TypeView]
    people: list[PersonRef]
    is_demo: bool


@dataclass(frozen=True, slots=True)
class OrganizationView:
    id: uuid.UUID
    name: str
    role: str
    is_center: bool


@dataclass(frozen=True, slots=True)
class MilestoneView:
    id: uuid.UUID
    title: str
    due_on: date
    original_due_on: date
    is_passed: bool
    passed_on: date | None
    step: Attention | None
    deviation: int
    version: int


@dataclass(frozen=True, slots=True)
class TaskView:
    id: uuid.UUID
    title: str
    status: str
    due_on: date | None
    assignee: PersonRef | None
    step: Attention | None


@dataclass(frozen=True, slots=True)
class DetailView:
    card: CardView
    description: str | None
    direction: str | None
    region: str | None
    organizations: list[OrganizationView]
    milestones: list[MilestoneView]
    subprojects: list[CardView]
    tasks: list[TaskView]
    question: tuple[str, date] | None
    last_decision: tuple[str, date] | None


@dataclass(frozen=True, slots=True)
class StateView:
    step: Attention | None
    deviation: int
    lag_days: int
    due_on: date


@dataclass(frozen=True, slots=True)
class MilestoneShift:
    id: uuid.UUID
    title: str
    before: Attention | None
    after: Attention | None


@dataclass(frozen=True, slots=True)
class WhatIfView:
    before: StateView
    after: StateView
    milestones: list[MilestoneShift]
    pult_before: dict[str, int]
    pult_after: dict[str, int]


# --------------------------------------------------------------------------------------
# Чтение
# --------------------------------------------------------------------------------------


def _name(names: Names | None, locale: str) -> str | None:
    if names is None:
        return None
    return localized_name(locale, ru=names.ru, uz_cyrl=names.uz_cyrl, uz_latn=names.uz_latn)


def _rows_of(ladder: Ladder) -> dict[Key, Row]:
    return {(row.section, row.entity_id): row for row in ladder.rows}


@dataclass(frozen=True, slots=True)
class _Context:
    """Всё, что нужно плитке кроме самой строки проекта, — считается один раз на запрос."""

    today: date
    now: datetime
    zone: ZoneInfo
    locale: str
    thresholds: metrics.Thresholds
    steps: dict[Key, Row]


def _card(row: ProjectRow, context: _Context) -> CardView:
    status = ProjectStatus(row.status)
    passed = sum(1 for mark in row.marks if mark.is_passed)
    figures = metrics.progress(
        status=status,
        started_on=row.started_on,
        due_on=row.due_on,
        today=context.today,
        passed_milestones=passed,
        total_milestones=len(row.marks),
        done_tasks=row.done_tasks,
        total_tasks=row.total_tasks,
    )
    ladder_row = context.steps.get((PROJECTS, row.id))
    upcoming = min(
        (mark for mark in row.marks if not mark.is_passed),
        key=lambda mark: mark.due_on,
        default=None,
    )

    impediment = None
    if row.impediment:
        # Строка без своей даты датируется последней правкой проекта: «обновлено» без
        # даты читалось бы как «сегодня», а это неправда.
        touched = local_date(row.impediment_updated_at or row.changed_at, context.zone)
        impediment = ImpedimentView(
            text=row.impediment,
            updated_on=touched,
            stale=metrics.impediment_stale(
                updated_on=touched, today=context.today, thresholds=context.thresholds
            ),
        )

    return CardView(
        id=row.id,
        code=row.code,
        title=row.title,
        type_code=row.type_code,
        type_name=_name(row.type_names, context.locale) or row.type_code,
        status=row.status,
        status_reason=row.status_reason,
        parent=(row.parent_id, row.parent_title or "") if row.parent_id else None,
        is_multiyear=row.is_multiyear,
        subprojects=row.subprojects,
        started_on=row.started_on,
        due_on=row.due_on,
        original_due_on=row.original_due_on,
        moves=metrics.moves_count(row.due_changes, zone=context.zone),
        responsible=(
            PersonRef(id=row.responsible_id, name=row.responsible_name)
            if row.responsible_id and row.responsible_name
            else None
        ),
        readiness=figures.readiness,
        lag_days=figures.lag_days,
        step=ladder_row.attention if ladder_row else None,
        deviation=ladder_row.deviation if ladder_row else 0,
        impediment=impediment,
        lead_outside=row.lead_outside,
        center_role=row.center_role,
        next_milestone=(
            MarkView(title=upcoming.title, due_on=upcoming.due_on, is_passed=False)
            if upcoming
            else None
        ),
        milestones_passed=passed,
        milestones_total=len(row.marks),
        tasks_done=row.done_tasks,
        tasks_total=row.total_tasks,
        marks=[
            MarkView(title=mark.title, due_on=mark.due_on, is_passed=mark.is_passed)
            for mark in row.marks
        ],
        version=row.version,
    )


def _ordered(cards: list[CardView], ladder: Ladder) -> list[CardView]:
    """Порядок раздела — порядок лестницы, затем идущее по плану, в конце закрытое.

    Строки со ступенью идут ровно так, как на Пульте: порядок задаёт сервер, и два экрана
    не имеют права показать одно и то же в разной очерёдности (ТЗ 4). Внутри остальных
    групп — по сроку: ближний срок — ближняя забота.
    """
    position = {row.entity_id: index for index, row in enumerate(ladder.rows)}

    def key(card: CardView) -> tuple[int, int, date]:
        if card.id in position:
            return (0, position[card.id], card.due_on)
        if ProjectStatus(card.status).is_terminal:
            return (2, 0, card.due_on)
        return (1, 0, card.due_on)

    return sorted(cards, key=key)


async def _context(
    session: AsyncSession, *, now: datetime, zone: ZoneInfo, locale: str
) -> tuple[_Context, Ladder]:
    today = local_date(now, zone)
    thresholds = await metrics.load_thresholds(session)
    ladder = await metrics.ladder(session, today=today, zone=zone, thresholds=thresholds)
    return (
        _Context(
            today=today,
            now=now,
            zone=zone,
            locale=locale,
            thresholds=thresholds,
            steps=_rows_of(ladder),
        ),
        ladder,
    )


async def load(
    session: AsyncSession, *, now: datetime, zone: ZoneInfo, locale: str, is_demo: bool
) -> ProjectsView:
    """Весь раздел одним запросом: плитки, типы с шаблонами, люди для формы."""
    context, ladder = await _context(session, now=now, zone=zone, locale=locale)
    rows = await read_model.projects(session)
    kinds = await read_model.project_types(session)
    people = await read_model.people(session)
    return ProjectsView(
        as_of=now,
        items=_ordered([_card(row, context) for row in rows], ladder),
        types=[
            TypeView(
                code=kind.code,
                name=_name(kind.names, locale) or kind.code,
                template=[
                    (_name(step.names, locale) or "", step.offset_days) for step in kind.template
                ],
            )
            for kind in kinds
        ],
        people=[PersonRef(id=person_id, name=name) for person_id, name in people],
        is_demo=is_demo,
    )


async def _row(session: AsyncSession, project_id: uuid.UUID) -> ProjectRow:
    rows = await read_model.projects(session, ids=[project_id])
    if not rows:
        raise NotFoundError("Проект не найден: его могли удалить")
    return rows[0]


async def detail(
    session: AsyncSession, *, project_id: uuid.UUID, now: datetime, zone: ZoneInfo, locale: str
) -> DetailView:
    """Карточка проекта — всё о нём на одном листе."""
    row = await _row(session, project_id)
    context, ladder = await _context(session, now=now, zone=zone, locale=locale)
    subprojects = await read_model.projects(session, parent_id=project_id)
    organizations = await read_model.organizations(session, project_id)
    tasks = await read_model.tasks(session, project_id)

    target = (DecisionTarget.PROJECT.value, project_id)
    question = (await pult_model.open_questions(session, [target])).get(target)
    decision = (await pult_model.last_decisions(session, [target])).get(target)

    def step(section: str, entity_id: uuid.UUID) -> Row | None:
        return context.steps.get((section, entity_id))

    return DetailView(
        card=_card(row, context),
        description=row.description,
        direction=_name(row.direction, locale),
        region=_name(row.region, locale),
        organizations=[
            OrganizationView(id=org.id, name=org.name, role=org.role, is_center=org.is_center)
            for org in organizations
        ],
        milestones=[
            MilestoneView(
                id=mark.id,
                title=mark.title,
                due_on=mark.due_on,
                original_due_on=mark.original_due_on,
                is_passed=mark.is_passed,
                passed_on=mark.passed_on,
                step=found.attention if (found := step(MILESTONES, mark.id)) else None,
                deviation=found.deviation if found else 0,
                version=mark.version,
            )
            for mark in row.marks
        ],
        subprojects=_ordered([_card(sub, context) for sub in subprojects], ladder),
        tasks=[
            TaskView(
                id=task.id,
                title=task.title,
                status=task.status,
                due_on=local_date(task.due_at, zone) if task.due_at else None,
                assignee=(
                    PersonRef(id=task.assignee_id, name=task.assignee_name)
                    if task.assignee_id and task.assignee_name
                    else None
                ),
                step=found.attention if (found := step("tasks", task.id)) else None,
            )
            for task in tasks
        ],
        question=(question.text, local_date(question.created_at, zone)) if question else None,
        last_decision=(
            (decision.kind, local_date(decision.created_at, zone)) if decision else None
        ),
    )


# --------------------------------------------------------------------------------------
# Запись
# --------------------------------------------------------------------------------------


async def create(
    session: AsyncSession, *, user: User, data: NewProject, today: date, locale: str
) -> uuid.UUID:
    """Новый проект за два обязательных поля — название и тип (ТЗ 3.1, 7).

    Вехи подставляются из шаблона типа: помощник выбирает «нормативный акт» и получает
    разработку, согласование, внесение готовыми строками, а не вспоминает их. Срок, если
    его не назвали, — по последней вехе шаблона. Исходный срок равен сроку: переносов у
    нового проекта нет.
    """
    title = validate_title(data.title)
    kinds = await read_model.project_types(session, codes=[data.type_code])
    if not kinds:
        raise RuleViolationError("Такого типа проекта нет среди действующих", detail=data.type_code)
    kind = kinds[0]

    offsets = [step.offset_days for step in kind.template]
    validate_horizon(data.started_on, *([data.due_on] if data.due_on else []))
    due_on = data.due_on or default_due_on(started_on=data.started_on, offsets=offsets)
    validate_horizon(due_on)
    validate_dates(started_on=data.started_on, due_on=due_on)

    parent: Project | None = None
    if data.parent_id is not None:
        parent = await session.get(Project, data.parent_id)
        if parent is None:
            raise NotFoundError("Программа не найдена: её могли удалить")
        validate_nesting(parent_has_parent=parent.parent_project_id is not None)
        if ProjectStatus(parent.status_code).is_terminal:
            raise RuleViolationError(
                "Программа завершена или отменена — новый подпроект в неё не входит"
            )
    validate_program(
        is_multiyear=data.is_multiyear,
        parent_is_multiyear=parent.is_multiyear if parent else None,
    )

    if data.responsible_id is not None and not await read_model.person_is_active(
        session, data.responsible_id
    ):
        raise NotFoundError("Ответственный не найден среди действующих сотрудников")

    project = Project(
        title=title,
        project_type_id=kind.id,
        parent_project_id=data.parent_id,
        is_multiyear=data.is_multiyear,
        started_on=data.started_on,
        due_on=due_on,
        original_due_on=due_on,
        status_code=ProjectStatus.IN_PROGRESS.value,
        responsible_person_id=data.responsible_id,
        created_by=user.id,
    )
    await add_with_code(
        session,
        project,
        assign=lambda: next_code(
            session,
            column=Project.code,
            prefix=PROJECT_CODE_PREFIX,
            digits=PROJECT_CODE_DIGITS,
            today=today,
        ),
    )

    planned_dates = template_dates(started_on=data.started_on, due_on=data.due_on, offsets=offsets)
    for step, planned in zip(kind.template, planned_dates, strict=True):
        session.add(
            Milestone(
                project_id=project.id,
                title=_name(step.names, locale) or step.names.ru,
                due_on=planned,
                original_due_on=planned,
                sort_order=step.sort_order,
            )
        )
    await session.flush()
    return project.id


async def _project(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFoundError("Проект не найден: его могли удалить")
    return project


async def set_status(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    status: ProjectStatus,
    reason: str | None,
    version: int,
) -> None:
    """Статус проекта; пауза и отмена — только с причиной (ТЗ 3.1).

    У остальных статусов причина стирается: «Причина: ждём финансирование» у проекта,
    который уже снова в работе, говорила бы неправду.
    """
    project = await _project(session, project_id)
    check_version(expected=version, actual=project.version)
    validate_status_reason(status=status, reason=reason)
    project.status_code = status.value
    project.status_reason = (reason or "").strip() or None if status.requires_reason else None
    await session.flush()


async def set_impediment(
    session: AsyncSession, *, project_id: uuid.UUID, text: str, version: int, now: datetime
) -> None:
    """«Что мешает» — одна строка с датой. Сохранить ту же строку — подтвердить её.

    Дата обновляется при каждом сохранении, даже если текст прежний: строку, которую
    помощник пересмотрел и оставил, устаревшей считать нельзя — ради этого дата и есть.
    """
    project = await _project(session, project_id)
    check_version(expected=version, actual=project.version)
    value = clean_impediment(text)
    project.impediment = value
    project.impediment_updated_at = now if value else None
    await session.flush()


def _validate_changes(row: ProjectRow, changes: Sequence[DueChange]) -> None:
    """Что можно сдвигать: срок самого проекта и сроки его непройденных вех."""
    if not changes:
        raise RuleViolationError("Сроки не менялись — считать нечего")
    if len(changes) > MAX_CHANGES:
        raise RuleViolationError(f"За один раз можно сдвинуть не больше {MAX_CHANGES} сроков")
    if ProjectStatus(row.status).is_terminal:
        # Закрытый проект не стоит в лестнице: считать по нему нечего, и «что если»
        # показал бы «ничего не изменится» там, где изменение просто некуда приложить.
        raise RuleViolationError("Завершённый или отменённый проект не пересчитывается")

    seen: set[Key] = set()
    marks = {mark.id: mark for mark in row.marks}
    for change in changes:
        key = (change.kind.value, change.id)
        if key in seen:
            raise RuleViolationError("Один и тот же срок указан дважды")
        seen.add(key)
        validate_horizon(change.due_on)
        if change.kind is ChangeKind.PROJECT:
            if change.id != row.id:
                raise RuleViolationError("Срок чужого проекта здесь не меняется")
            validate_dates(started_on=row.started_on, due_on=change.due_on)
            continue
        mark = marks.get(change.id)
        if mark is None:
            raise NotFoundError("Веха не найдена в этом проекте: её могли удалить")
        if mark.is_passed:
            raise RuleViolationError(
                "Пройденную веху не переносят", detail=f"«{mark.title}» уже пройдена"
            )


def _counts(ladder: Ladder) -> dict[str, int]:
    return {step.value: ladder.count(step) for step in STEPS}


async def what_if(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    changes: Sequence[DueChange],
    now: datetime,
    zone: ZoneInfo,
) -> WhatIfView:
    """Что станет с проектом, его вехами и Пультом при других сроках. Без записи.

    Обе лестницы считает один код по одному снимку (`metrics.what_if`): разница между
    ними — ровно следствие новых сроков. Отставание «после» — та же функция готовности и
    отставания с новым сроком проекта.
    """
    row = await _row(session, project_id)
    _validate_changes(row, changes)

    today = local_date(now, zone)
    thresholds = await metrics.load_thresholds(session)
    due = {
        (PROJECTS if change.kind is ChangeKind.PROJECT else MILESTONES, change.id): change.due_on
        for change in changes
    }
    try:
        before, after = await metrics.what_if(
            session, today=today, zone=zone, changes=due, thresholds=thresholds
        )
    except KeyError as missing:
        # Проверка выше видела веху непройденной, а снимок лестницы — уже нет: её прошли
        # или проект закрыли в эти доли секунды. Это не поломка, а устаревшая картина.
        raise ConflictError(
            "Проект изменили, пока шёл расчёт. Обновите карточку и посчитайте ещё раз"
        ) from missing
    rows_before, rows_after = _rows_of(before), _rows_of(after)

    status = ProjectStatus(row.status)
    passed = sum(1 for mark in row.marks if mark.is_passed)

    def state(rows: dict[Key, Row], due_on: date) -> StateView:
        found = rows.get((PROJECTS, row.id))
        figures = metrics.progress(
            status=status,
            started_on=row.started_on,
            due_on=due_on,
            today=today,
            passed_milestones=passed,
            total_milestones=len(row.marks),
            done_tasks=row.done_tasks,
            total_tasks=row.total_tasks,
        )
        return StateView(
            step=found.attention if found else None,
            deviation=found.deviation if found else 0,
            lag_days=figures.lag_days,
            due_on=due_on,
        )

    def attention(rows: dict[Key, Row], mark_id: uuid.UUID) -> Attention | None:
        found = rows.get((MILESTONES, mark_id))
        return found.attention if found else None

    return WhatIfView(
        before=state(rows_before, row.due_on),
        after=state(rows_after, due.get((PROJECTS, row.id), row.due_on)),
        milestones=[
            MilestoneShift(
                id=mark.id,
                title=mark.title,
                before=attention(rows_before, mark.id),
                after=attention(rows_after, mark.id),
            )
            for mark in row.marks
        ],
        pult_before=_counts(before),
        pult_after=_counts(after),
    )


async def apply_dates(
    session: AsyncSession, *, project_id: uuid.UUID, changes: Sequence[DueChange]
) -> None:
    """«Применить»: новые сроки записываются — объектами, с журналом и версией.

    Исходный срок не трогается: по нему видно, что срок переносили (ТЗ 3.1). Перенос
    позже журнал запомнит как перенос — из него считаются «переносов: N» на плитке и
    «Держим ли мы свои сроки?» на Пульте.
    """
    row = await _row(session, project_id)
    _validate_changes(row, changes)
    if any(change.version is None for change in changes):
        raise RuleViolationError("У каждого срока нужна версия записи, которую вы видели")

    project = await _project(session, project_id)
    marks = await read_model.milestones_of(
        session,
        project_id,
        [change.id for change in changes if change.kind is ChangeKind.MILESTONE],
    )
    # Сначала все версии, потом правки: отказ по второй вехе не должен оставлять в сессии
    # уже сдвинутый срок первой — всё или ничего, как и обещает «Применить».
    targets: list[tuple[Project | Milestone, date]] = []
    for change in changes:
        target: Project | Milestone | None = (
            project if change.kind is ChangeKind.PROJECT else marks.get(change.id)
        )
        if target is None:
            # Веху удалили между проверкой и правкой — та же устаревшая картина.
            raise NotFoundError("Веха не найдена в этом проекте: её могли удалить")
        check_version(expected=change.version or 0, actual=target.version)
        targets.append((target, change.due_on))
    for target, due_on in targets:
        target.due_on = due_on
    await session.flush()
