"""Календарь — сборка раздела и годовые циклы (ТЗ 2, 3.1, 5, 11).

Форма — договор экрана `frontend/src/sections/calendar/model.ts`, утверждённого заказчиком
28.09.2026 на вымышленных данных той же формы (CLAUDE.md, цикл блока «экран → API»).

**Числа — из `app.services.metrics`, и больше ниоткуда** (инвариант 2): ступень и
отклонение даты — строка той же лестницы, что у Пульта; горячие дни, их порог и окно —
функции того же сервиса. Дата годового цикла ступени не имеет (V16): Пульт циклов не знает,
и календарь не спорит с ним.

Цикл хранит правило, даты разворачивает `app.domain.cycles` — в базу они не пишутся.
Отмена цикла — по версии, которую видел человек (инвариант 15).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import LADDER, Attention, Row
from app.domain.calendar import (
    MAX_RANGE_DAYS,
    CalendarKind,
    HotDay,
    Mark,
    ProjectEnd,
    ends_with_milestone,
)
from app.domain.clock import local_date
from app.domain.cycles import (
    TITLE_MAX_LENGTH,
    CycleRule,
    dates_between,
    horizon,
    next_date,
    occurrences,
    validate_rule,
)
from app.domain.decisions import DecisionTarget
from app.domain.errors import NotFoundError, RuleViolationError, check_version
from app.repos import calendar as read_model
from app.repos import projects as project_model
from app.repos import tasks as task_model
from app.repos.calendar import CycleRow, DatedRow
from app.repos.models import User, YearlyCycle
from app.services import metrics
from app.services.projects import PersonRef

SECTION = {
    CalendarKind.PROJECT: "projects",
    CalendarKind.MILESTONE: "milestones",
    CalendarKind.TASK: "tasks",
    CalendarKind.DECISION: "decisions",
    CalendarKind.IJRO: "ijro",
    CalendarKind.PREPARATION: "preparations",
}
"""Раздел строки лестницы по виду даты — как их называет снимок `app.repos.attention`."""


@dataclass(frozen=True, slots=True)
class OwnerRef:
    id: uuid.UUID
    title: str


@dataclass(frozen=True, slots=True)
class RuleView:
    rule: CycleRule
    month: int
    day: int
    every_years: int
    anchor_year: int


@dataclass(frozen=True, slots=True)
class ItemView:
    id: str
    """Номер записи; у даты цикла — `цикл:дата`, у цикла дат много."""

    kind: CalendarKind
    date: date
    title: str | None
    decision_kind: str | None
    owner: OwnerRef | None
    target_kind: str
    target_id: uuid.UUID
    responsible: PersonRef | None
    step: Attention | None
    deviation: int
    is_done: bool
    ends_project: bool
    cycle: RuleView | None


@dataclass(frozen=True, slots=True)
class CalendarView:
    as_of: datetime
    since: date
    until: date
    items: list[ItemView]
    overdue: list[ItemView]
    hot_days: list[HotDay]
    hot_ahead: list[HotDay]
    hot_window_days: int
    hot_threshold: int
    horizon_to: date
    people: list[PersonRef]
    projects: list[OwnerRef]
    is_demo: bool


@dataclass(frozen=True, slots=True)
class CycleView:
    id: uuid.UUID
    title: str
    rule: RuleView
    owner: OwnerRef | None
    responsible: PersonRef | None
    next_date: date | None
    dates: list[date]
    version: int


@dataclass(frozen=True, slots=True)
class PreviewView:
    dates: list[date]
    next_date: date | None


@dataclass(frozen=True, slots=True)
class NewCycle:
    title: str
    rule: CycleRule
    month: int
    day: int
    every_years: int
    anchor_year: int
    project_id: uuid.UUID | None
    responsible_id: uuid.UUID | None


# --------------------------------------------------------------------------------------
# Раздел
# --------------------------------------------------------------------------------------


def _rank(step: Attention | None) -> int:
    return step.rank if step is not None else len(LADDER)


def _person(person_id: uuid.UUID | None, name: str | None) -> PersonRef | None:
    return PersonRef(id=person_id, name=name) if person_id is not None and name else None


def _dated(rows: Sequence[DatedRow], steps: Mapping[tuple[str, uuid.UUID], Row]) -> list[ItemView]:
    """Даты записей; срок проекта в день его вехи — строкой вехи «и срок проекта» (V15)."""
    merged = ends_with_milestone(
        (
            ProjectEnd(project_id=row.id, due_on=row.on, is_done=row.is_done)
            for row in rows
            if row.kind is CalendarKind.PROJECT
        ),
        [
            Mark(
                milestone_id=row.id,
                project_id=row.project_id,
                due_on=row.on,
                is_done=row.is_done,
            )
            for row in rows
            if row.kind is CalendarKind.MILESTONE and row.project_id is not None
        ],
    )
    ends_of = {milestone: project for project, milestone in merged.items()}

    def step_of(kind: CalendarKind, entity_id: uuid.UUID) -> Row | None:
        return steps.get((SECTION[kind], entity_id))

    items: list[ItemView] = []
    for row in rows:
        if row.kind is CalendarKind.PROJECT and row.id in merged:
            continue
        found = step_of(row.kind, row.id)
        ends = ends_of.get(row.id) if row.kind is CalendarKind.MILESTONE else None
        if ends is not None:
            # Ступень — старшая из двух: вопрос по проекту не пропадает оттого, что строка
            # — веха.
            end = step_of(CalendarKind.PROJECT, ends)
            if end is not None and (found is None or end.attention.rank < found.attention.rank):
                found = end
        target_kind, target_id = _target(row)
        items.append(
            ItemView(
                id=str(row.id),
                kind=row.kind,
                date=row.on,
                title=row.title,
                decision_kind=row.decision_kind,
                owner=(
                    OwnerRef(id=row.project_id, title=row.project_title)
                    if row.kind is not CalendarKind.PROJECT
                    and row.project_id is not None
                    and row.project_title is not None
                    else None
                ),
                target_kind=target_kind,
                target_id=target_id,
                responsible=_person(row.responsible_id, row.responsible_name),
                step=found.attention if found is not None and not row.is_done else None,
                deviation=found.deviation if found is not None and not row.is_done else 0,
                is_done=row.is_done,
                ends_project=ends is not None,
                cycle=None,
            )
        )
    return items


def _target(row: DatedRow) -> tuple[str, uuid.UUID]:
    """Какую карточку открывает касание: проект, задачу — или само решение.

    Веха открывает свой проект: у вехи отдельной карточки нет. Своей карточки нет и у
    решения — касание открывает то, по чему оно принято; решение по поручению Ижро (блок 2)
    остаётся решением.
    """
    if row.kind is CalendarKind.PROJECT:
        return "project", row.id
    if row.kind is CalendarKind.MILESTONE and row.project_id is not None:
        return "project", row.project_id
    if row.kind is CalendarKind.DECISION and row.about is not None:
        about, about_id = row.about
        if about == DecisionTarget.TASK.value:
            return "task", about_id
        if about in (DecisionTarget.PROJECT.value, DecisionTarget.MILESTONE.value) and (
            row.project_id is not None
        ):
            return "project", row.project_id
    return row.kind.value, row.id


def _rule(row: CycleRow) -> RuleView:
    return RuleView(
        rule=CycleRule(row.rule),
        month=row.month,
        day=row.day,
        every_years=row.every_years,
        anchor_year=row.anchor_year,
    )


def _cycle_dates(rows: Sequence[CycleRow], *, since: date, until: date) -> list[ItemView]:
    """Даты циклов с `since` по `until` — и прошедшие, без ступени (V16)."""
    items: list[ItemView] = []
    for row in rows:
        rule = _rule(row)
        for day in dates_between(
            rule=rule.rule,
            month=rule.month,
            day=rule.day,
            every_years=rule.every_years,
            anchor_year=rule.anchor_year,
            since=since,
            until=until,
        ):
            items.append(
                ItemView(
                    id=f"{row.id}:{day.isoformat()}",
                    kind=CalendarKind.CYCLE,
                    date=day,
                    title=row.title,
                    decision_kind=None,
                    owner=(
                        OwnerRef(id=row.project_id, title=row.project_title)
                        if row.project_id is not None and row.project_title is not None
                        else None
                    ),
                    target_kind="cycle",
                    target_id=row.id,
                    responsible=_person(row.responsible_id, row.responsible_name),
                    step=None,
                    deviation=0,
                    is_done=False,
                    ends_project=False,
                    cycle=rule,
                )
            )
    return items


def _ordered(items: list[ItemView]) -> list[ItemView]:
    """По дню, внутри дня — ступень лестницы, затем вид даты, затем название."""
    return sorted(
        items, key=lambda item: (item.date, _rank(item.step), item.kind.order, item.title or "")
    )


def validate_range(since: date, until: date) -> None:
    if until < since:
        raise RuleViolationError("Конец окна раньше начала")
    if (until - since).days + 1 > MAX_RANGE_DAYS:
        raise RuleViolationError(f"Окно календаря — не больше {MAX_RANGE_DAYS} дней")


async def open_dates(
    session: AsyncSession, *, since: date, until: date, today: date, zone: ZoneInfo
) -> list[tuple[date, CalendarKind]]:
    """Незакрытые даты дней `[since, until]` — из них `metrics.hot_days` считает горячие дни.

    Те же даты, что у раздела: сроки записей со слиянием срока проекта с вехой (V15) и даты
    годовых циклов до горизонта. Нужны «Управлению» — предпросмотру порогов горячих дней,
    который считает тем же кодом и ничего не пишет.
    """
    items = _dated(await read_model.dated(session, since=since, until=until, zone=zone), {})
    items += _cycle_dates(
        await read_model.cycles(session), since=since, until=min(until, horizon(today))
    )
    return [(item.date, item.kind) for item in items if not item.is_done]


async def load(
    session: AsyncSession,
    *,
    since: date,
    until: date,
    now: datetime,
    zone: ZoneInfo,
    is_demo: bool,
) -> CalendarView:
    """Запрошенные дни, «срок прошёл» и горячие дни — одной сборкой.

    Даты читаются сразу за запрошенные дни и окно «где неделя перегружена?»: ответ
    карточки не зависит от месяца, который смотрят, а срок проекта сливается с вехой по
    всем датам окна, иначе горячий день на стыке считался бы по-разному.
    """
    validate_range(since, until)
    today = local_date(now, zone)
    thresholds = await metrics.load_thresholds(session)
    ladder = await metrics.ladder(session, today=today, zone=zone, thresholds=thresholds)
    steps = {(row.section, row.entity_id): row for row in ladder.rows}
    window_from, window_to = metrics.hot_window(today, thresholds)
    first, last = min(since, window_from), max(until, window_to)
    horizon_to = horizon(today)

    everything = _ordered(
        _dated(await read_model.dated(session, since=first, until=last, zone=zone), steps)
        + _cycle_dates(await read_model.cycles(session), since=first, until=min(last, horizon_to))
    )
    open_dates = [(item.date, item.kind) for item in everything if not item.is_done]
    overdue = _ordered(_dated(await read_model.overdue(session, before=today, zone=zone), steps))

    return CalendarView(
        as_of=now,
        since=since,
        until=until,
        items=[item for item in everything if since <= item.date <= until],
        overdue=overdue,
        hot_days=metrics.hot_days(
            open_dates, since=since, until=until, today=today, thresholds=thresholds
        ),
        hot_ahead=metrics.hot_days(
            open_dates, since=window_from, until=window_to, today=today, thresholds=thresholds
        ),
        hot_window_days=thresholds.hot_window_days,
        hot_threshold=thresholds.hot_day_threshold,
        horizon_to=horizon_to,
        people=[
            PersonRef(id=person_id, name=name)
            for person_id, name in await project_model.people(session)
        ],
        projects=[
            OwnerRef(id=project_id, title=title)
            for project_id, _, title in await task_model.project_refs(session)
        ],
        is_demo=is_demo,
    )


# --------------------------------------------------------------------------------------
# Годовые циклы
# --------------------------------------------------------------------------------------


def _next(rule: RuleView, today: date) -> date | None:
    return next_date(
        rule=rule.rule,
        month=rule.month,
        day=rule.day,
        every_years=rule.every_years,
        anchor_year=rule.anchor_year,
        since=today,
    )


def _dates(rule: RuleView, today: date) -> list[date]:
    return occurrences(
        rule=rule.rule,
        month=rule.month,
        day=rule.day,
        every_years=rule.every_years,
        anchor_year=rule.anchor_year,
        since=today,
    )


def _view(row: CycleRow, today: date) -> CycleView:
    rule = _rule(row)
    return CycleView(
        id=row.id,
        title=row.title,
        rule=rule,
        owner=(
            OwnerRef(id=row.project_id, title=row.project_title)
            if row.project_id is not None and row.project_title is not None
            else None
        ),
        responsible=_person(row.responsible_id, row.responsible_name),
        next_date=_next(rule, today),
        dates=_dates(rule, today),
        version=row.version,
    )


async def cycles(session: AsyncSession, *, today: date) -> list[CycleView]:
    """Все действующие циклы по ближайшей дате — и те, у которых за год вперёд дат нет.

    В сетке цикл виден только датами на год вперёд, а цикл «раз в три года» два года из
    трёх их не имеет: без списка его нельзя было бы ни открыть, ни отменить.
    """
    views = [_view(row, today) for row in await read_model.cycles(session)]
    return sorted(views, key=lambda view: (view.next_date or date.max, view.title))


async def cycle(session: AsyncSession, *, cycle_id: uuid.UUID, today: date) -> CycleView:
    row = await read_model.cycle(session, cycle_id)
    if row is None:
        raise NotFoundError("Цикл не найден: его могли отменить")
    return _view(row, today)


def preview(rule: RuleView, *, today: date) -> PreviewView:
    """Даты будущего цикла до записи: помощник видит, что заводит. Ничего не пишет.

    Правило здесь не проверяется: «дат нет» — это и есть ответ, который форма показывает
    словами («ближайшая — …» или «такого дня нет ни в одном году»).
    """
    return PreviewView(dates=_dates(rule, today), next_date=_next(rule, today))


def _clean_title(title: str) -> str:
    cleaned = " ".join(title.split())
    if not cleaned:
        raise RuleViolationError("Нужно название цикла")
    if len(cleaned) > TITLE_MAX_LENGTH:
        raise RuleViolationError(f"Название цикла — не длиннее {TITLE_MAX_LENGTH} знаков")
    return cleaned


async def create(session: AsyncSession, *, user: User, data: NewCycle, today: date) -> uuid.UUID:
    """Новый цикл — обязательно название и правило, у которого есть хоть одна дата (ТЗ 7).

    У ежегодного и ежеквартального цикла «раз в N лет» не спрашивается: хранится один и год
    начала — текущий. `user` не записывается в цикл — автора помнит журнал.
    """
    del user
    title = _clean_title(data.title)
    every = data.every_years if data.rule is CycleRule.EVERY_N_YEARS else 1
    anchor = data.anchor_year if data.rule is CycleRule.EVERY_N_YEARS else today.year
    validate_rule(
        rule=data.rule,
        month=data.month,
        day=data.day,
        every_years=every,
        anchor_year=anchor,
        today=today,
    )
    if data.project_id is not None:
        is_open = await task_model.project_is_open(session, data.project_id)
        if is_open is None:
            raise NotFoundError("Проект не найден: его могли удалить")
        if not is_open:
            raise RuleViolationError("Проект завершён или отменён — новый цикл в него не входит")
    if data.responsible_id is not None and not await project_model.person_is_active(
        session, data.responsible_id
    ):
        raise NotFoundError("Ответственный не найден среди действующих сотрудников")

    found = YearlyCycle(
        title=title,
        rule=data.rule.value,
        # У ежеквартального месяц не спрашивается: кварталы календарные.
        month=data.month if data.rule is not CycleRule.QUARTERLY else 1,
        day=data.day,
        every_years=every,
        anchor_year=anchor,
        project_id=data.project_id,
        responsible_person_id=data.responsible_id,
        is_active=True,
    )
    session.add(found)
    await session.flush()
    return found.id


async def cancel(session: AsyncSession, *, cycle_id: uuid.UUID, version: int) -> None:
    """Отмена цикла — по версии; цикл не удаляется, запись о нём остаётся в журнале."""
    found = await session.get(YearlyCycle, cycle_id)
    if found is None or not found.is_active:
        raise NotFoundError("Цикл не найден: его могли отменить")
    check_version(expected=version, actual=found.version)
    found.is_active = False
    await session.flush()
