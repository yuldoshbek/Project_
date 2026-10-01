"""Ижро — реестр поручений, карточка, отметки и правки помощника.

Форма ответа — договор экрана `frontend/src/sections/ijro/model.ts`: экран утверждён
заказчиком 30.09.2026 на вымышленных данных той же формы, и API написан под него
(CLAUDE.md, цикл блока). Решения и вопросы по поручению — прежние `POST /api/v1/decisions`
и `/questions` с `target_type = ijro_assignment`: кнопки те же, что на Пульте.

Роль подписывает действие (V35): отметку и реплику ставят оба (`CurrentUser`); этап,
проблему, «запрошено продление», сопоставление ФИО и задачу — помощник (`Assistant`).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SettingsDep, is_demo
from app.api.security import Assistant, CurrentUser
from app.api.transaction import transactional_router
from app.domain.clock import now_utc
from app.domain.comments import BODY_MAX_LENGTH
from app.domain.ijro import DuePrecision, IjroSource, IjroState, LifeSource, MarkKind
from app.domain.ijro_control import TEXT_MAX_LENGTH
from app.domain.people import Role
from app.services import ijro as service

router = transactional_router(tags=["ижро"])

Step = Literal["awaiting_decision", "overdue", "burning", "blocked_by_others", "silent"]
Verdict = Literal["on_track", "behind", "little_data"]
ChangeClass = Literal[
    "new", "unchanged", "text_changed", "responsible_changed", "due_moved", "vanished",
    "unrecognized",
]  # fmt: skip


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str | None


class DocumentOut(BaseModel):
    id: uuid.UUID
    kind: str
    code: str
    issued_on: date | None
    title: str
    source: IjroSource


class DocumentBriefOut(BaseModel):
    id: uuid.UUID
    code: str
    source: IjroSource


class LifeOut(BaseModel):
    on: date
    source: LifeSource


class QuestionRefOut(BaseModel):
    id: uuid.UUID
    text: str
    asked_on: date


class DecisionRefOut(BaseModel):
    id: uuid.UUID
    kind: str
    decided_on: date


class AssignmentRowOut(BaseModel):
    id: uuid.UUID
    document: DocumentBriefOut
    band: str | None
    band_order: int
    content: str
    due_on: date | None
    due_precision: DuePrecision
    original_due_on: date | None
    interim_on: date | None
    extensions: int
    extension_requested: bool
    responsible_raw: str
    responsible: PersonOut | None
    lead_organization: OrganizationOut | None
    is_co_executor: bool
    stage: IjroState
    stage_changed_on: date
    step: Step | None
    deviation: int
    sign_of_life: LifeOut | None
    has_problem: bool
    question: QuestionRefOut | None
    last_decision: DecisionRefOut | None
    tasks: int
    first_seen_on: date
    version: int


class ExtensionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: date = Field(alias="from", serialization_alias="from")
    to: date
    on: date
    batch_id: uuid.UUID | None
    kind: Literal["extension", "correction"]


class MarkOut(BaseModel):
    id: uuid.UUID
    kind: MarkKind
    promised_on: date | None
    comment: str | None
    made_at: datetime
    author: Role | None


class LinkedTaskOut(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    status: str
    step: Step | None
    due_on: date | None
    moved_on: date


class CommentOut(BaseModel):
    id: uuid.UUID
    text: str
    author: Role | None
    created_at: datetime


class ImportOut(BaseModel):
    batch_id: uuid.UUID | None
    table_on: date
    file: str


class AssignmentCardOut(AssignmentRowOut):
    document: DocumentOut  # type: ignore[assignment]
    mechanism: str | None
    extension_history: list[ExtensionOut]
    problem: str | None
    proposal: str | None
    problem_updated_on: date | None
    marks: list[MarkOut]
    linked_tasks: list[LinkedTaskOut]
    comments: list[CommentOut]
    suggestions: list[PersonOut]
    import_: ImportOut = Field(alias="import", serialization_alias="import")

    model_config = ConfigDict(populate_by_name=True)


class WallCellOut(BaseModel):
    id: uuid.UUID
    band: str | None
    stage: IjroState
    step: Step | None


class CallOut(BaseModel):
    person: PersonOut
    open: int


class WallDocumentOut(BaseModel):
    document: DocumentOut
    done: int
    total: int
    cells: list[WallCellOut]
    call_for_report: CallOut | None


# --- двенадцать ответов: у каждого своя форма, список под действием — всегда `rows` ---


class OldestOut(BaseModel):
    id: uuid.UUID
    days: int


class PersonLoadOut(BaseModel):
    person: PersonOut | None
    responsible_raw: str
    overdue: int
    burning: int


class BurningAnswer(BaseModel):
    key: Literal["burning"]
    burning: int
    overdue: int
    oldest: OldestOut | None
    by_person: list[PersonLoadOut]
    rows: list[uuid.UUID]


class OrganizationGroupOut(BaseModel):
    organization: OrganizationOut
    count: int
    rows: list[uuid.UUID]


class ForeignAnswer(BaseModel):
    key: Literal["foreign"]
    count: int
    organizations: list[OrganizationGroupOut]
    rows: list[uuid.UUID]


class SilentWorstOut(BaseModel):
    id: uuid.UUID
    person: PersonOut | None
    responsible_raw: str
    days: int


class SilentAnswer(BaseModel):
    key: Literal["silent"]
    count: int
    worst: SilentWorstOut | None
    rows: list[uuid.UUID]


class DocumentShareOut(BaseModel):
    document: DocumentOut
    done: int
    total: int


class DocumentsAnswer(BaseModel):
    key: Literal["documents"]
    worst: DocumentShareOut | None
    rows: list[uuid.UUID]


class ChronicSampleOut(BaseModel):
    id: uuid.UUID
    original_due_on: date
    due_on: date
    extensions: int


class ChronicAnswer(BaseModel):
    key: Literal["chronic"]
    count: int
    sample: ChronicSampleOut | None
    rows: list[uuid.UUID]


class YearEndAnswer(BaseModel):
    key: Literal["year_end"]
    upcoming: int
    closed: int
    window_days: int
    min_closed: int
    verdict: Verdict
    rows: list[uuid.UUID]


class ReportUpAnswer(BaseModel):
    key: Literal["report_up"]
    count: int
    freshest_on: date | None
    rows: list[uuid.UUID]


class AwaitingAnswer(BaseModel):
    key: Literal["awaiting"]
    count: int
    oldest: OldestOut | None
    rows: list[uuid.UUID]


class ExtensionRequestedAnswer(BaseModel):
    key: Literal["extension_requested"]
    count: int
    rows: list[uuid.UUID]


class ReturnedAnswer(BaseModel):
    key: Literal["returned"]
    count: int
    oldest: OldestOut | None
    rows: list[uuid.UUID]


class WithoutTasksAnswer(BaseModel):
    key: Literal["without_tasks"]
    count: int
    total: int
    rows: list[uuid.UUID]


class BatchRefOut(BaseModel):
    id: uuid.UUID
    table_on: date
    file: str
    source: IjroSource | None


class LastBatchAnswer(BaseModel):
    key: Literal["last_batch"]
    batch: BatchRefOut | None
    created: int
    changed: int
    vanished: int
    pending_extensions: int
    rows: list[uuid.UUID]


QuestionAnswer = Annotated[
    BurningAnswer
    | ForeignAnswer
    | SilentAnswer
    | DocumentsAnswer
    | ChronicAnswer
    | YearEndAnswer
    | ReportUpAnswer
    | AwaitingAnswer
    | ExtensionRequestedAnswer
    | ReturnedAnswer
    | WithoutTasksAnswer
    | LastBatchAnswer,
    Field(discriminator="key"),
]


class ThresholdsOut(BaseModel):
    burn_days: int
    quiet_days: int
    near_due_days: int
    pace_window_days: int
    min_closed_for_pace: int


class BatchOut(BaseModel):
    id: uuid.UUID
    file: str
    source: IjroSource | None
    table_on: date
    uploaded_at: datetime
    state: Literal["applied", "discarded"]
    counts: dict[ChangeClass, int]


class IjroResponse(BaseModel):
    as_of: datetime
    table_on: date | None
    thresholds: ThresholdsOut
    questions: list[QuestionAnswer]
    items: list[AssignmentRowOut]
    documents: list[WallDocumentOut]
    people: list[PersonOut]
    organizations: list[OrganizationOut]
    batches: list[BatchOut]
    is_demo: bool


class SpravkaLineOut(BaseModel):
    id: uuid.UUID
    place: str
    content: str
    due_on: date | None
    due_precision: DuePrecision
    responsible: str
    problem: str
    proposal: str | None
    problem_updated_on: date | None


class TaskPrefillOut(BaseModel):
    title: str
    type_code: Literal["ijro_report"]
    assignee_id: uuid.UUID | None
    due_on: date | None
    ijro_assignment_id: uuid.UUID


class Created(BaseModel):
    """Что создано: идентификатор — кнопке «Отменить» и тесту."""

    id: uuid.UUID


class CreatedTaskOut(Created):
    code: str


def _zone(settings: Any) -> ZoneInfo:
    return ZoneInfo(settings.timezone)


@router.get("/ijro", response_model=IjroResponse, summary="Ижро: раздел целиком")
async def read_ijro(user: CurrentUser, session: SessionDep, settings: SettingsDep) -> IjroResponse:
    view = await service.load(
        session, now=now_utc(), zone=_zone(settings), is_demo=is_demo(settings)
    )
    return IjroResponse.model_validate(asdict(view))


@router.get(
    "/ijro/assignments/{assignment_id}",
    response_model=AssignmentCardOut,
    response_model_by_alias=True,
    summary="Карточка поручения",
)
async def read_assignment(
    assignment_id: uuid.UUID, user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> AssignmentCardOut:
    view = await service.card(
        session, assignment_id=assignment_id, now=now_utc(), zone=_zone(settings)
    )
    extra = asdict(view)
    row = extra.pop("row")
    extra["import"] = extra.pop("import_")
    return AssignmentCardOut.model_validate(row | extra)


@router.get(
    "/ijro/spravka",
    response_model=list[SpravkaLineOut],
    summary="Справка по проблемным поручениям — «что докладывать наверх?»",
)
async def read_spravka(
    user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> list[SpravkaLineOut]:
    lines = await service.spravka(session, now=now_utc(), zone=_zone(settings))
    return [SpravkaLineOut.model_validate(asdict(line)) for line in lines]


class MarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: MarkKind
    promised_on: date | None = None
    comment: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)


@router.post(
    "/ijro/assignments/{assignment_id}/marks",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Контрольная отметка — оба пользователя",
)
async def create_mark(
    assignment_id: uuid.UUID,
    body: MarkRequest,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> Created:
    mark_id = await service.mark(
        session,
        user=user,
        assignment_id=assignment_id,
        kind=body.kind,
        promised_on=body.promised_on,
        comment=body.comment,
        now=now_utc(),
        zone=_zone(settings),
    )
    return Created(id=mark_id)


class StageRequest(BaseModel):
    stage: IjroState
    version: int


@router.put(
    "/ijro/assignments/{assignment_id}/stage",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Этап поручения",
)
async def update_stage(
    assignment_id: uuid.UUID, body: StageRequest, user: Assistant, session: SessionDep
) -> None:
    await service.set_stage(
        session,
        assignment_id=assignment_id,
        stage=body.stage,
        version=body.version,
        now=now_utc(),
    )


class ProblemRequest(BaseModel):
    problem: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)
    proposal: str | None = Field(default=None, max_length=TEXT_MAX_LENGTH)
    version: int


@router.put(
    "/ijro/assignments/{assignment_id}/problem",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Проблема и предложение",
)
async def update_problem(
    assignment_id: uuid.UUID, body: ProblemRequest, user: Assistant, session: SessionDep
) -> None:
    await service.set_problem(
        session,
        assignment_id=assignment_id,
        problem=body.problem,
        proposal=body.proposal,
        version=body.version,
        now=now_utc(),
    )


class ExtensionRequest(BaseModel):
    value: bool
    version: int


@router.put(
    "/ijro/assignments/{assignment_id}/extension-request",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="«Запрошено продление»",
)
async def update_extension_request(
    assignment_id: uuid.UUID, body: ExtensionRequest, user: Assistant, session: SessionDep
) -> None:
    await service.set_extension_requested(
        session, assignment_id=assignment_id, value=body.value, version=body.version
    )


class ResponsibleRequest(BaseModel):
    person_id: uuid.UUID
    version: int


@router.put(
    "/ijro/assignments/{assignment_id}/responsible",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Сопоставить написание из таблицы с сотрудником",
)
async def update_responsible(
    assignment_id: uuid.UUID, body: ResponsibleRequest, user: Assistant, session: SessionDep
) -> None:
    await service.match_person(
        session, assignment_id=assignment_id, person_id=body.person_id, version=body.version
    )


class CommentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=BODY_MAX_LENGTH)


@router.post(
    "/ijro/assignments/{assignment_id}/comments",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Реплика в ленте хода исполнения",
)
async def create_comment(
    assignment_id: uuid.UUID, body: CommentRequest, user: CurrentUser, session: SessionDep
) -> Created:
    comment_id = await service.comment(
        session, user=user, assignment_id=assignment_id, text=body.text
    )
    return Created(id=comment_id)


@router.get(
    "/ijro/assignments/{assignment_id}/task-prefill",
    response_model=TaskPrefillOut,
    summary="«Разложить на задачу»: что покажет подтверждение",
)
async def read_task_prefill(
    assignment_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> TaskPrefillOut:
    prefill = await service.task_prefill(session, assignment_id=assignment_id)
    return TaskPrefillOut.model_validate(asdict(prefill))


@router.post(
    "/ijro/assignments/{assignment_id}/tasks",
    response_model=CreatedTaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="«Разложить на задачу»: задача из поручения",
)
async def create_task(
    assignment_id: uuid.UUID, user: Assistant, session: SessionDep, settings: SettingsDep
) -> CreatedTaskOut:
    created = await service.create_task(
        session, user=user, assignment_id=assignment_id, now=now_utc(), zone=_zone(settings)
    )
    return CreatedTaskOut(id=created.id, code=created.code)
