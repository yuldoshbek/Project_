"""Пульт — один запрос на весь экран.

Форма ответа — договор экрана `frontend/src/sections/pult/model.ts`: экран утверждён
заказчиком на вымышленных данных той же формы, и API написан под него, а не наоборот
(CLAUDE.md, цикл блока). Эндпоинта, которому нет места на экране, здесь нет.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import Query
from pydantic import BaseModel

from app.api.deps import SessionDep, SettingsDep, is_demo
from app.api.security import CurrentUser
from app.api.transaction import transactional_router
from app.domain.clock import now_utc
from app.domain.pult import PeriodKind
from app.services import pult as service

router = transactional_router(tags=["пульт"])


class Person(BaseModel):
    id: uuid.UUID
    name: str


class Question(BaseModel):
    id: uuid.UUID
    text: str
    asked_on: date


class LastDecision(BaseModel):
    kind: str
    decided_on: date


class Row(BaseModel):
    section: str
    entity_id: uuid.UUID
    title: str | None
    decision_kind: str | None
    context: str | None
    step: str
    deviation: int
    due_on: date | None
    original_due_on: date | None
    responsible: Person | None
    question: Question | None
    last_decision: LastDecision | None
    target_type: str
    target_id: uuid.UUID


class Holder(BaseModel):
    person: Person
    counts: dict[str, int]
    total: int
    worst: str


class Change(BaseModel):
    kind: str
    section: str
    entity_id: uuid.UUID
    title: str | None
    at: datetime
    moved: dict[str, date] | None


class MovedItem(BaseModel):
    section: str
    entity_id: uuid.UUID
    title: str | None
    original_due_on: date
    due_on: date | None
    moves: int


class DeadlineMoves(BaseModel):
    period_days: int
    moves: int
    total_shift_days: int
    items: list[MovedItem]


class PultResponse(BaseModel):
    as_of: datetime
    last_visit_at: datetime | None
    rows: list[Row]
    counts: dict[str, int]
    on_track: int
    holders: list[Holder]
    changes: list[Change]
    deadline_moves: DeadlineMoves
    is_demo: bool


def _row(row: service.RowView) -> Row:
    return Row(
        section=row.section,
        entity_id=row.entity_id,
        title=row.title,
        decision_kind=row.decision_kind,
        context=row.context,
        step=row.step.value,
        deviation=row.deviation,
        due_on=row.due_on,
        original_due_on=row.original_due_on,
        responsible=Person(id=row.responsible.id, name=row.responsible.name)
        if row.responsible
        else None,
        question=Question(
            id=row.question.id, text=row.question.text, asked_on=row.question.asked_on
        )
        if row.question
        else None,
        last_decision=LastDecision(
            kind=row.last_decision.kind, decided_on=row.last_decision.decided_on
        )
        if row.last_decision
        else None,
        target_type=row.target_type,
        target_id=row.target_id,
    )


def _holder(holder: service.HolderView) -> Holder:
    return Holder(
        person=Person(id=holder.person.id, name=holder.person.name),
        counts=holder.counts,
        total=holder.total,
        worst=holder.worst.value,
    )


def _moves(moves: service.MovesView) -> DeadlineMoves:
    return DeadlineMoves(
        period_days=moves.period_days,
        moves=moves.moves,
        total_shift_days=moves.total_shift_days,
        items=[
            MovedItem(
                section=item.section,
                entity_id=item.entity_id,
                title=item.title,
                original_due_on=item.original_due_on,
                due_on=item.due_on,
                moves=item.moves,
            )
            for item in moves.items
        ],
    )


@router.get("/pult", response_model=PultResponse, summary="Пульт: что требует внимания")
async def read_pult(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> PultResponse:
    view = await service.load(
        session,
        viewer=user,
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
        is_demo=is_demo(settings),
    )
    return PultResponse(
        as_of=view.as_of,
        last_visit_at=view.last_visit_at,
        rows=[_row(row) for row in view.rows],
        counts=view.counts,
        on_track=view.on_track,
        holders=[_holder(holder) for holder in view.holders],
        changes=[
            Change(
                kind=change.kind.value,
                section=change.section,
                entity_id=change.entity_id,
                title=change.title,
                at=change.at,
                moved={"from": change.moved[0], "to": change.moved[1]} if change.moved else None,
            )
            for change in view.changes
        ],
        deadline_moves=_moves(view.deadline_moves),
        is_demo=view.is_demo,
    )


class Totals(BaseModel):
    created_projects: int
    created_tasks: int
    closed_tasks: int
    closed_projects: int
    passed_milestones: int
    decisions_made: int
    decisions_done: int
    moves: int
    shift_days: int


class ReportDecision(BaseModel):
    kind: str
    title: str | None
    decided_on: date
    state: str
    done_on: date | None


class ReportResponse(BaseModel):
    period: str
    start: date
    end: date
    generated_at: datetime
    totals: Totals
    counts: dict[str, int]
    on_track: int
    rows: list[Row]
    more_rows: int
    holders: list[Holder]
    decisions: list[ReportDecision]
    deadline_moves: DeadlineMoves
    is_demo: bool


@router.get(
    "/pult/report",
    response_model=ReportResponse,
    summary="Отчёт недели или месяца — вкладка Пульта, печать в PDF",
)
async def read_report(
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    period: PeriodKind = PeriodKind.WEEK,
    offset: int = Query(default=0, ge=0, le=24, description="Сколько периодов назад"),
) -> ReportResponse:
    view = await service.report(
        session,
        viewer=user,
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
        kind=period,
        offset=offset,
        is_demo=is_demo(settings),
    )
    totals = view.totals
    return ReportResponse(
        period=view.kind.value,
        start=view.start,
        end=view.end,
        generated_at=view.generated_at,
        totals=Totals(
            created_projects=totals.created_projects,
            created_tasks=totals.created_tasks,
            closed_tasks=totals.closed_tasks,
            closed_projects=totals.closed_projects,
            passed_milestones=totals.passed_milestones,
            decisions_made=totals.decisions_made,
            decisions_done=totals.decisions_done,
            moves=totals.moves,
            shift_days=totals.shift_days,
        ),
        counts=view.counts,
        on_track=view.on_track,
        rows=[_row(row) for row in view.rows],
        more_rows=view.more_rows,
        holders=[_holder(holder) for holder in view.holders],
        decisions=[
            ReportDecision(
                kind=decision.kind,
                title=decision.title,
                decided_on=decision.decided_on,
                state=decision.state,
                done_on=decision.done_on,
            )
            for decision in view.decisions
        ],
        deadline_moves=_moves(view.deadline_moves),
        is_demo=view.is_demo,
    )
