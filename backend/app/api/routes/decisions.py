"""Решения руководителя и вопросы к нему — кнопки строки Пульта.

Четыре пути ровно под четыре действия экрана: решить, отменить решение, спросить,
отменить вопрос. Решает только руководитель, спрашивает только помощник — оба правила
стоят на входе (`Leader`, `Assistant`), а не внутри сценария.
"""

from __future__ import annotations

import uuid
from zoneinfo import ZoneInfo

from fastapi import status
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, SettingsDep
from app.api.security import Assistant, Leader
from app.api.transaction import transactional_router
from app.domain.clock import local_date, now_utc
from app.domain.decisions import TEXT_MAX_LENGTH, DecisionKind
from app.services import decisions as service

router = transactional_router(tags=["решения"])


class DecisionRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    kind: DecisionKind
    text: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)


class QuestionRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    text: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)


class Created(BaseModel):
    """Что создано: идентификатор нужен кнопке «Отменить»."""

    id: uuid.UUID


@router.post(
    "/decisions",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Решение руководителя",
)
async def create_decision(
    body: DecisionRequest, user: Leader, session: SessionDep, settings: SettingsDep
) -> Created:
    now = now_utc()
    decision = await service.decide(
        session,
        user=user,
        target_type=body.target_type,
        target_id=body.target_id,
        kind=body.kind,
        text=body.text,
        today=local_date(now, ZoneInfo(settings.timezone)),
        now=now,
    )
    return Created(id=decision.id)


@router.delete(
    "/decisions/{decision_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отменить решение сразу после касания",
)
async def delete_decision(decision_id: uuid.UUID, user: Leader, session: SessionDep) -> None:
    await service.undo_decision(session, user=user, decision_id=decision_id, now=now_utc())


@router.post(
    "/questions",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Вопрос руководителю",
)
async def create_question(body: QuestionRequest, user: Assistant, session: SessionDep) -> Created:
    question = await service.ask(
        session,
        user=user,
        target_type=body.target_type,
        target_id=body.target_id,
        text=body.text,
    )
    return Created(id=question.id)


@router.delete(
    "/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отменить вопрос сразу после него",
)
async def delete_question(question_id: uuid.UUID, user: Assistant, session: SessionDep) -> None:
    await service.undo_question(session, user=user, question_id=question_id, now=now_utc())
