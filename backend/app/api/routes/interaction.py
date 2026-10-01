"""Взаимодействие — письма, организации, соглашения.

Форма ответа — договор экрана `frontend/src/sections/interaction/model.ts`: экран утверждён
заказчиком 01.10.2026 на вымышленных данных той же формы, и API написан под него
(CLAUDE.md, цикл блока). Решения и вопросы по письму и соглашению — прежние
`/decisions` и `/questions` с `target_type = letter | agreement`: кнопки строки Пульта.

Роль подписывает действие: письмо вносит и ответ отмечает помощник (`Assistant`), ответ
оценивает руководитель (`Leader`, V38), следующий шаг соглашения — помощник.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SettingsDep, is_demo
from app.api.security import Assistant, CurrentUser, Leader
from app.api.transaction import transactional_router
from app.domain.clock import local_date, now_utc
from app.domain.interaction import (
    NEXT_STEP_MAX_LENGTH,
    NUMBER_MAX_LENGTH,
    SUBJECT_MAX_LENGTH,
    AgreementKind,
    Direction,
    LetterState,
    Rating,
)
from app.services import interaction as service

router = transactional_router(tags=["взаимодействие"])

Step = Literal["awaiting_decision", "overdue", "burning", "blocked_by_others", "silent"]
OrganizationKind = Literal["ministry", "agency", "khokimiyat", "international", "company"]


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str


class OrganizationRefOut(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None


class LinkOut(BaseModel):
    type: Literal["project", "ijro", "preparation"]
    id: uuid.UUID
    title: str


class ReplyOut(BaseModel):
    number: str | None
    sent_on: date


class LetterOut(BaseModel):
    id: uuid.UUID
    direction: Direction
    organization: OrganizationRefOut
    subject: str
    number: str | None
    sent_on: date
    due_on: date | None
    author: PersonOut | None
    link: LinkOut | None
    answered_on: date | None
    reply: ReplyOut | None
    rating: Rating | None
    state: LetterState
    step: Step | None
    deviation: int
    days: int
    version: int


class AgreementOut(BaseModel):
    id: uuid.UUID
    organization: OrganizationRefOut
    kind: AgreementKind
    title: str
    signed_on: date
    valid_until: date | None
    next_step: str | None
    next_step_on: date | None
    responsible: PersonOut | None
    moved_on: date
    sleeping: bool
    quiet_days: int
    step: Step | None
    deviation: int
    version: int


class SpeedOut(BaseModel):
    letters: int
    median_days: int | None


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None
    kind: OrganizationKind
    is_founded_by_agency: bool
    phone: str | None
    email: str | None
    waiting: int
    to_answer: int
    agreement_count: int
    sleeping: int
    overdue_steps: int
    ijro_lead: int
    project_count: int
    speed: SpeedOut
    ratings: dict[Rating, int]


class IjroRefOut(BaseModel):
    id: uuid.UUID
    place: str
    content: str
    step: Step | None


class ProjectRefOut(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    role: Literal["customer", "executor", "co_executor", "lead_agency"]


class OrganizationCardOut(OrganizationOut):
    letters: list[LetterOut]
    agreements: list[AgreementOut]
    ijro: list[IjroRefOut]
    projects: list[ProjectRefOut]


# --- четыре ответа: у каждого своя форма, список под действием — всегда `rows` ---


class WaitingGroupOut(BaseModel):
    organization: OrganizationRefOut
    count: int
    oldest_days: int
    rows: list[uuid.UUID]


class NotAnsweringAnswer(BaseModel):
    key: Literal["not_answering"]
    count: int
    organizations: list[WaitingGroupOut]
    rows: list[uuid.UUID]


class NearestOut(BaseModel):
    id: uuid.UUID
    due_on: date
    days: int


class ToAnswerAnswer(BaseModel):
    key: Literal["to_answer"]
    count: int
    overdue: int
    nearest: NearestOut | None
    rows: list[uuid.UUID]


class MeasuredOut(BaseModel):
    organization: OrganizationRefOut
    median_days: int
    letters: int


class SpeedAnswer(BaseModel):
    key: Literal["speed"]
    measured: list[MeasuredOut]
    little_data: int
    min_letters: int
    rows: list[uuid.UUID]


class OldestOut(BaseModel):
    id: uuid.UUID
    days: int


class SleepingAnswer(BaseModel):
    key: Literal["sleeping"]
    count: int
    oldest: OldestOut | None
    rows: list[uuid.UUID]


QuestionAnswer = Annotated[
    NotAnsweringAnswer | ToAnswerAnswer | SpeedAnswer | SleepingAnswer,
    Field(discriminator="key"),
]


class ThresholdsOut(BaseModel):
    burn_days: int
    quiet_days: int
    sleeping_days: int
    min_letters: int


class InteractionResponse(BaseModel):
    as_of: datetime
    thresholds: ThresholdsOut
    questions: list[QuestionAnswer]
    letters: list[LetterOut]
    organizations: list[OrganizationOut]
    agreements: list[AgreementOut]
    people: list[PersonOut]
    choices: list[OrganizationRefOut]
    is_demo: bool


class Created(BaseModel):
    id: uuid.UUID


@router.get(
    "/interaction", response_model=InteractionResponse, summary="Взаимодействие: раздел целиком"
)
async def read_interaction(
    user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> InteractionResponse:
    view = await service.load(
        session, now=now_utc(), zone=ZoneInfo(settings.timezone), is_demo=is_demo(settings)
    )
    return InteractionResponse.model_validate(asdict(view))


@router.get(
    "/interaction/organizations/{organization_id}",
    response_model=OrganizationCardOut,
    summary="Карточка организации: письма, соглашения, поручения, проекты",
)
async def read_organization(
    organization_id: uuid.UUID, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> OrganizationCardOut:
    card = await service.organization(
        session, organization_id=organization_id, now=now_utc(), zone=ZoneInfo(settings.timezone)
    )
    body = asdict(card)
    return OrganizationCardOut.model_validate(body.pop("organization") | body)


class NewLetterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Direction
    organization_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=SUBJECT_MAX_LENGTH)
    number: str | None = Field(default=None, max_length=NUMBER_MAX_LENGTH)
    sent_on: date
    due_on: date | None = None
    author_id: uuid.UUID | None = None


@router.post(
    "/interaction/letters",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Новое письмо",
)
async def create_letter(
    body: NewLetterRequest, user: Assistant, session: SessionDep, settings: SettingsDep
) -> Created:
    letter_id = await service.add_letter(
        session,
        data=service.NewLetter(
            direction=body.direction,
            organization_id=body.organization_id,
            subject=body.subject,
            number=body.number,
            sent_on=body.sent_on,
            due_on=body.due_on,
            author_id=body.author_id,
        ),
        today=local_date(now_utc(), ZoneInfo(settings.timezone)),
    )
    return Created(id=letter_id)


class AnswerRequest(BaseModel):
    on: date
    number: str | None = Field(default=None, max_length=NUMBER_MAX_LENGTH)
    version: int


@router.put(
    "/interaction/letters/{letter_id}/answer",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Ответ получен или мы ответили",
)
async def answer_letter(
    letter_id: uuid.UUID,
    body: AnswerRequest,
    user: Assistant,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    await service.answer(
        session,
        letter_id=letter_id,
        on=body.on,
        number=body.number,
        version=body.version,
        today=local_date(now_utc(), ZoneInfo(settings.timezone)),
    )


class RatingRequest(BaseModel):
    rating: Rating | None
    version: int


@router.put(
    "/interaction/letters/{letter_id}/rating",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Оценка полученного ответа — руководитель",
)
async def rate_letter(
    letter_id: uuid.UUID, body: RatingRequest, user: Leader, session: SessionDep
) -> None:
    await service.rate(session, letter_id=letter_id, rating=body.rating, version=body.version)


class NextStepRequest(BaseModel):
    next_step: str | None = Field(default=None, max_length=NEXT_STEP_MAX_LENGTH)
    next_step_on: date | None = None
    version: int


@router.put(
    "/interaction/agreements/{agreement_id}/next-step",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Следующий шаг соглашения",
)
async def update_next_step(
    agreement_id: uuid.UUID, body: NextStepRequest, user: Assistant, session: SessionDep
) -> None:
    await service.next_step(
        session,
        agreement_id=agreement_id,
        text=body.next_step,
        on=body.next_step_on,
        version=body.version,
        now=now_utc(),
    )
