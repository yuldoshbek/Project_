"""Календарь — даты раздела и годовые циклы.

Форма ответа — договор экрана `frontend/src/sections/calendar/model.ts`: экран утверждён
заказчиком 28.09.2026 на вымышленных данных той же формы, и API написан под него
(CLAUDE.md, цикл блока). Эндпоинта, которому нет места на экране, здесь нет.

Смотрят оба; цикл заводит и отменяет помощник (`Assistant`). Даты цикла до записи ничего не
записывают и доступны обоим — как «что если» у проектов.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SettingsDep, is_demo
from app.api.security import Assistant, CurrentUser
from app.api.transaction import transactional_router
from app.domain.calendar import CalendarKind, HotDay
from app.domain.clock import local_date, now_utc
from app.domain.cycles import TITLE_MAX_LENGTH, CycleRule
from app.services import calendar as service

router = transactional_router(tags=["календарь"])


class Ref(BaseModel):
    id: uuid.UUID
    name: str


class Owner(BaseModel):
    id: uuid.UUID
    title: str


class Target(BaseModel):
    kind: str
    id: uuid.UUID


class Rule(BaseModel):
    rule: CycleRule
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    every_years: int = Field(ge=1, le=10)
    anchor_year: int = Field(ge=1900, le=2200)


class Item(BaseModel):
    id: str
    kind: CalendarKind
    date: date
    title: str | None
    decision_kind: str | None
    owner: Owner | None
    target: Target
    responsible: Ref | None
    step: str | None
    deviation: int
    is_done: bool
    ends_project: bool
    cycle: Rule | None


class Hot(BaseModel):
    date: date
    count: int
    kinds: dict[CalendarKind, int]


class Range(BaseModel):
    # `from` — слово языка, поэтому поле называется иначе, а в ответе — как в договоре.
    model_config = ConfigDict(populate_by_name=True)

    from_: date = Field(alias="from")
    to: date


class CalendarResponse(BaseModel):
    as_of: datetime
    range: Range
    items: list[Item]
    overdue: list[Item]
    hot_days: list[Hot]
    hot_ahead: list[Hot]
    hot_window_days: int
    hot_threshold: int
    horizon_to: date
    people: list[Ref]
    projects: list[Owner]
    is_demo: bool


def _rule(view: service.RuleView) -> Rule:
    return Rule(
        rule=view.rule,
        month=view.month,
        day=view.day,
        every_years=view.every_years,
        anchor_year=view.anchor_year,
    )


def _item(view: service.ItemView) -> Item:
    return Item(
        id=view.id,
        kind=view.kind,
        date=view.date,
        title=view.title,
        decision_kind=view.decision_kind,
        owner=Owner(id=view.owner.id, title=view.owner.title) if view.owner else None,
        target=Target(kind=view.target_kind, id=view.target_id),
        responsible=(
            Ref(id=view.responsible.id, name=view.responsible.name) if view.responsible else None
        ),
        step=view.step.value if view.step else None,
        deviation=view.deviation,
        is_done=view.is_done,
        ends_project=view.ends_project,
        cycle=_rule(view.cycle) if view.cycle else None,
    )


def _hot(day: HotDay) -> Hot:
    return Hot(date=day.date, count=day.count, kinds=day.kinds)


@router.get("/calendar", response_model=CalendarResponse, summary="Календарь: даты окна дней")
async def read_calendar(
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    since: Annotated[date, Query(alias="from", description="Первый день окна")],
    until: Annotated[date, Query(alias="to", description="Последний день окна включительно")],
) -> CalendarResponse:
    view = await service.load(
        session,
        since=since,
        until=until,
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
        is_demo=is_demo(settings),
    )
    return CalendarResponse(
        as_of=view.as_of,
        range=Range(from_=view.since, to=view.until),
        items=[_item(item) for item in view.items],
        overdue=[_item(item) for item in view.overdue],
        hot_days=[_hot(day) for day in view.hot_days],
        hot_ahead=[_hot(day) for day in view.hot_ahead],
        hot_window_days=view.hot_window_days,
        hot_threshold=view.hot_threshold,
        horizon_to=view.horizon_to,
        people=[Ref(id=person.id, name=person.name) for person in view.people],
        projects=[Owner(id=project.id, title=project.title) for project in view.projects],
        is_demo=view.is_demo,
    )


class Cycle(BaseModel):
    id: uuid.UUID
    title: str
    rule: CycleRule
    month: int
    day: int
    every_years: int
    anchor_year: int
    owner: Owner | None
    responsible: Ref | None
    next_date: date | None


class CycleDetail(Cycle):
    dates: list[date]
    version: int


def _cycle_fields(view: service.CycleView) -> dict[str, object]:
    return {
        "id": view.id,
        "title": view.title,
        "rule": view.rule.rule,
        "month": view.rule.month,
        "day": view.rule.day,
        "every_years": view.rule.every_years,
        "anchor_year": view.rule.anchor_year,
        "owner": Owner(id=view.owner.id, title=view.owner.title) if view.owner else None,
        "responsible": (
            Ref(id=view.responsible.id, name=view.responsible.name) if view.responsible else None
        ),
        "next_date": view.next_date,
    }


def _detail(view: service.CycleView) -> CycleDetail:
    return CycleDetail(**_cycle_fields(view), dates=view.dates, version=view.version)


def _today(settings: SettingsDep) -> date:
    return local_date(now_utc(), ZoneInfo(settings.timezone))


@router.get(
    "/cycles",
    response_model=list[Cycle],
    summary="Годовые циклы: все действующие, по ближайшей дате",
)
async def read_cycles(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> list[Cycle]:
    return [
        Cycle(**_cycle_fields(view))
        for view in await service.cycles(session, today=_today(settings))
    ]


@router.get(
    "/cycles/{cycle_id}", response_model=CycleDetail, summary="Годовой цикл: правило и даты"
)
async def read_cycle(
    cycle_id: uuid.UUID, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> CycleDetail:
    return _detail(await service.cycle(session, cycle_id=cycle_id, today=_today(settings)))


class Preview(BaseModel):
    dates: list[date]
    next_date: date | None


@router.post(
    "/cycles/preview",
    response_model=Preview,
    summary="Даты будущего цикла — без записи",
)
async def preview_cycle(body: Rule, user: CurrentUser, settings: SettingsDep) -> Preview:
    view = service.preview(
        service.RuleView(
            rule=body.rule,
            month=body.month,
            day=body.day,
            every_years=body.every_years,
            anchor_year=body.anchor_year,
        ),
        today=_today(settings),
    )
    return Preview(dates=view.dates, next_date=view.next_date)


class NewCycleRequest(Rule):
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    project_id: uuid.UUID | None = None
    responsible_id: uuid.UUID | None = None


@router.post(
    "/cycles",
    response_model=CycleDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Новый годовой цикл: название и правило",
)
async def create_cycle(
    body: NewCycleRequest, user: Assistant, session: SessionDep, settings: SettingsDep
) -> CycleDetail:
    today = _today(settings)
    cycle_id = await service.create(
        session,
        user=user,
        data=service.NewCycle(
            title=body.title,
            rule=body.rule,
            month=body.month,
            day=body.day,
            every_years=body.every_years,
            anchor_year=body.anchor_year,
            project_id=body.project_id,
            responsible_id=body.responsible_id,
        ),
        today=today,
    )
    return _detail(await service.cycle(session, cycle_id=cycle_id, today=today))


class CancelRequest(BaseModel):
    version: int


@router.post(
    "/cycles/{cycle_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отменить цикл — по версии; запись остаётся в журнале",
)
async def cancel_cycle(
    cycle_id: uuid.UUID, body: CancelRequest, user: Assistant, session: SessionDep
) -> None:
    await service.cancel(session, cycle_id=cycle_id, version=body.version)
