"""Пульт — один запрос на весь экран.

Форма ответа — договор экрана `frontend/src/sections/pult/model.ts`: экран утверждён
заказчиком на вымышленных данных той же формы, и API написан под него, а не наоборот
(CLAUDE.md, цикл блока). Эндпоинта, которому нет места на экране, здесь нет.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.api.deps import SessionDep, SettingsDep
from app.api.security import CurrentUser
from app.api.transaction import transactional_router
from app.domain.clock import now_utc
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


@router.get("/pult", response_model=PultResponse, summary="Пульт: что требует внимания")
async def read_pult(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> PultResponse:
    view = await service.load(
        session,
        viewer=user,
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
        # Вымышленные данные живут везде, кроме рабочего контура (инвариант 11): экран
        # обязан это сказать, иначе вымышленную строку однажды примут за настоящую.
        is_demo=settings.env != "production",
    )
    return PultResponse(
        as_of=view.as_of,
        last_visit_at=view.last_visit_at,
        rows=[
            Row(
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
            for row in view.rows
        ],
        counts=view.counts,
        on_track=view.on_track,
        holders=[
            Holder(
                person=Person(id=holder.person.id, name=holder.person.name),
                counts=holder.counts,
                total=holder.total,
                worst=holder.worst.value,
            )
            for holder in view.holders
        ],
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
        deadline_moves=DeadlineMoves(
            period_days=view.deadline_moves.period_days,
            moves=view.deadline_moves.moves,
            total_shift_days=view.deadline_moves.total_shift_days,
            items=[
                MovedItem(
                    section=item.section,
                    entity_id=item.entity_id,
                    title=item.title,
                    original_due_on=item.original_due_on,
                    due_on=item.due_on,
                    moves=item.moves,
                )
                for item in view.deadline_moves.items
            ],
        ),
        is_demo=view.is_demo,
    )
