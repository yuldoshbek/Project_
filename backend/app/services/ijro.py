"""Ижро — реестр поручений, карточка, контрольные отметки и правки помощника (ТЗ 3.3, 5).

Форма — договор экрана `frontend/src/sections/ijro/model.ts`, утверждённого заказчиком
30.09.2026 на вымышленных данных той же формы (CLAUDE.md, цикл блока «экран → API»).

**Числа — из `app.services.metrics`** (инвариант 2): ступень строки считает тот же
`build_ladder`, что строит Пульт, двенадцать ответов и стена — `app.domain.ijro_control`
через сервис показателей. Здесь — сборка экрана и правки.

**Роль подписывает действие** (инвариант 13, допущение V35): контрольную отметку и
реплику ставят оба; этап, проблему, «запрошено продление», сопоставление ФИО и задачу из
поручения — помощник. Проверка роли стоит на входе (`app.api.routes.ijro`).

**Привоз меняет только поля источника** (инвариант 4): всё, что правится здесь — этап,
проблема, предложение, признак продления, сопоставленный сотрудник, — принадлежит нам.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import ijro_control as rules
from app.domain.attention import Attention, sort_key
from app.domain.clock import local_date
from app.domain.comments import CommentTarget, validate_body
from app.domain.decisions import DecisionTarget
from app.domain.errors import NotFoundError, RuleViolationError, check_version
from app.domain.ijro import (
    AliasSource,
    DuePrecision,
    IjroState,
    ImportState,
    MarkKind,
    normalize_person_name,
    split_responsible,
)
from app.domain.ijro_control import Answer, BatchEffect, Line, Question
from app.repos import ijro as read_model
from app.repos import pult as pult_model
from app.repos.ijro import AssignmentRecord, BatchRecord, DocumentRecord
from app.repos.models import (
    Comment,
    IjroAssignment,
    IjroControlMark,
    IjroPersonAlias,
    Person,
    User,
)
from app.services import metrics, tasks

TASK_TYPE = "ijro_report"
"""Тип задачи из поручения — «подготовка сведений по Ижро» (V34)."""

CHANGE_CLASSES = (
    "new",
    "unchanged",
    "text_changed",
    "responsible_changed",
    "due_moved",
    "vanished",
    "unrecognized",
)
"""Классы строк привоза (ТЗ 7) — у каждой партии в истории все семь, пустые нулём."""


# ---------------------------------------------------------------------------
# Виды экрана
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PersonRef:
    id: uuid.UUID
    name: str


@dataclass(frozen=True, slots=True)
class OrganizationRef:
    id: uuid.UUID
    name: str
    short_name: str | None


@dataclass(frozen=True, slots=True)
class DocumentRef:
    id: uuid.UUID
    kind: str
    code: str
    issued_on: date | None
    title: str
    source: str


@dataclass(frozen=True, slots=True)
class DocumentBrief:
    id: uuid.UUID
    code: str
    source: str


@dataclass(frozen=True, slots=True)
class LifeRef:
    on: date
    source: str


@dataclass(frozen=True, slots=True)
class QuestionRef:
    id: uuid.UUID
    text: str
    asked_on: date


@dataclass(frozen=True, slots=True)
class DecisionRef:
    id: uuid.UUID
    kind: str
    decided_on: date


@dataclass(frozen=True, slots=True)
class RowView:
    id: uuid.UUID
    document: DocumentBrief
    band: str | None
    band_order: int
    content: str
    due_on: date | None
    due_precision: str
    original_due_on: date | None
    interim_on: date | None
    extensions: int
    extension_requested: bool
    responsible_raw: str
    responsible: PersonRef | None
    lead_organization: OrganizationRef | None
    is_co_executor: bool
    stage: str
    stage_changed_on: date
    step: str | None
    deviation: int
    sign_of_life: LifeRef | None
    has_problem: bool
    question: QuestionRef | None
    last_decision: DecisionRef | None
    tasks: int
    first_seen_on: date
    version: int


@dataclass(frozen=True, slots=True)
class WallCellView:
    id: uuid.UUID
    band: str | None
    stage: str
    step: str | None


@dataclass(frozen=True, slots=True)
class CallView:
    person: PersonRef
    open: int


@dataclass(frozen=True, slots=True)
class WallView:
    document: DocumentRef
    done: int
    total: int
    cells: list[WallCellView]
    call_for_report: CallView | None


@dataclass(frozen=True, slots=True)
class ThresholdsView:
    burn_days: int
    quiet_days: int
    near_due_days: int
    pace_window_days: int
    min_closed_for_pace: int


@dataclass(frozen=True, slots=True)
class BatchView:
    id: uuid.UUID
    file: str
    source: str | None
    table_on: date
    uploaded_at: datetime
    state: str
    counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class IjroView:
    as_of: datetime
    table_on: date | None
    thresholds: ThresholdsView
    questions: list[dict[str, Any]]
    items: list[RowView]
    documents: list[WallView]
    people: list[PersonRef]
    organizations: list[OrganizationRef]
    batches: list[BatchView]
    is_demo: bool


@dataclass(frozen=True, slots=True)
class MarkView:
    id: uuid.UUID
    kind: str
    promised_on: date | None
    comment: str | None
    made_at: datetime
    author: str | None


@dataclass(frozen=True, slots=True)
class LinkedTaskView:
    id: uuid.UUID
    code: str
    title: str
    status: str
    step: str | None
    due_on: date | None
    moved_on: date


@dataclass(frozen=True, slots=True)
class CommentView:
    id: uuid.UUID
    text: str
    author: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ImportRef:
    batch_id: uuid.UUID | None
    table_on: date
    file: str


@dataclass(frozen=True, slots=True)
class CardView:
    """Карточка: строка реестра и всё длинное, что списку не нужно."""

    row: RowView
    document: DocumentRef
    mechanism: str | None
    extension_history: list[dict[str, Any]]
    problem: str | None
    proposal: str | None
    problem_updated_on: date | None
    marks: list[MarkView]
    linked_tasks: list[LinkedTaskView]
    comments: list[CommentView]
    suggestions: list[PersonRef]
    import_: ImportRef


@dataclass(frozen=True, slots=True)
class SpravkaLine:
    id: uuid.UUID
    place: str
    content: str
    due_on: date | None
    due_precision: str
    responsible: str
    problem: str
    proposal: str | None
    problem_updated_on: date | None


@dataclass(frozen=True, slots=True)
class TaskPrefill:
    title: str
    type_code: str
    assignee_id: uuid.UUID | None
    due_on: date | None
    ijro_assignment_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class CreatedTask:
    id: uuid.UUID
    code: str


# ---------------------------------------------------------------------------
# Снимок: строки, ступени, порядок
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Snapshot:
    records: list[AssignmentRecord]
    """В порядке лестницы."""

    lines: list[Line]
    rows: list[RowView]
    documents: dict[uuid.UUID, DocumentRecord]
    people: dict[uuid.UUID, str]
    organizations: dict[uuid.UUID, read_model.OrganizationRecord]


def _document_ref(document: DocumentRecord) -> DocumentRef:
    return DocumentRef(
        id=document.id,
        kind=document.kind,
        code=document.code,
        issued_on=document.issued_on,
        title=document.title,
        source=document.source,
    )


def _place(code: str, band: str | None) -> str:
    return f"{code} · {band}" if band else code


async def _snapshot(
    session: AsyncSession,
    *,
    today: date,
    zone: ZoneInfo,
    thresholds: metrics.Thresholds,
    ids: list[uuid.UUID] | None = None,
) -> _Snapshot:
    """Строки реестра со ступенями — фиксированным числом запросов на весь реестр."""
    records = await read_model.records(session, zone=zone, ids=ids)
    documents = {document.id: document for document in await read_model.documents(session)}
    people = dict(await read_model.people(session))
    organizations = await read_model.organizations(
        session, {r.lead_organization_id for r in records if r.lead_organization_id}
    )
    targets = [(DecisionTarget.IJRO_ASSIGNMENT.value, record.id) for record in records]
    questions = await pult_model.open_questions(session, targets)
    decisions = await pult_model.last_decisions(session, targets)

    def asked(record: AssignmentRecord) -> date | None:
        question = questions.get((DecisionTarget.IJRO_ASSIGNMENT.value, record.id))
        return local_date(question.created_at, zone) if question else None

    # Ступень — только у открытых: сданное и снятое в лестнице не стоят (V32).
    ladder = metrics.steps(
        [read_model.item_of(record, asked(record)) for record in records if record.is_open],
        today=today,
        thresholds=thresholds,
    )

    def order(record: AssignmentRecord) -> tuple[Any, ...]:
        row = ladder.get(record.id)
        step = row.attention if row else Attention.ON_TRACK
        code = documents[record.document_id].code if record.document_id in documents else ""
        return (
            sort_key(step, row.deviation if row else 0, record.due_on),
            code,
            record.band_sort,
            str(record.id),
        )

    records.sort(key=order)

    band_order: dict[uuid.UUID, int] = {}
    for document_id in {record.document_id for record in records}:
        own = sorted(
            (r for r in records if r.document_id == document_id),
            key=lambda r: (r.band_sort, str(r.id)),
        )
        band_order.update({r.id: index for index, r in enumerate(own)})

    lines: list[Line] = []
    rows: list[RowView] = []
    for record in records:
        ladder_row = ladder.get(record.id)
        step = ladder_row.attention if ladder_row else None
        deviation = ladder_row.deviation if ladder_row else 0
        life = record.life
        state = IjroState(record.state)
        lines.append(
            Line(
                id=record.id,
                document_id=record.document_id,
                state=state,
                state_changed_on=record.state_changed_on,
                step=step,
                deviation=deviation,
                due_on=record.due_on,
                due_precision=record.due_precision,
                original_due_on=record.original_due_on,
                extensions=record.extensions,
                extension_requested=record.extension_requested,
                responsible_person_id=record.responsible_person_id,
                responsible_raw=record.responsible_raw,
                lead_organization_id=record.lead_organization_id,
                is_co_executor=record.is_co_executor,
                quiet=rules.quiet_days(life, first_seen_on=record.first_seen_on, today=today),
                has_problem=record.problem is not None,
                problem_updated_on=record.problem_updated_on,
                tasks=record.tasks,
                first_seen_on=record.first_seen_on,
            )
        )
        document = documents[record.document_id]
        question = questions.get((DecisionTarget.IJRO_ASSIGNMENT.value, record.id))
        decision = decisions.get((DecisionTarget.IJRO_ASSIGNMENT.value, record.id))
        lead = (
            organizations.get(record.lead_organization_id) if record.lead_organization_id else None
        )
        person = record.responsible_person_id
        rows.append(
            RowView(
                id=record.id,
                document=DocumentBrief(id=document.id, code=document.code, source=document.source),
                band=record.band,
                band_order=band_order[record.id],
                content=record.content,
                due_on=record.due_on,
                due_precision=record.due_precision.value,
                original_due_on=record.original_due_on,
                interim_on=rules.interim_on(
                    first_seen_on=record.first_seen_on, due_on=record.due_on
                ),
                extensions=record.extensions,
                extension_requested=record.extension_requested,
                responsible_raw=record.responsible_raw,
                responsible=(
                    PersonRef(id=person, name=people[person])
                    if person is not None and person in people
                    else None
                ),
                lead_organization=(
                    OrganizationRef(id=lead.id, name=lead.name, short_name=lead.short_name)
                    if lead
                    else None
                ),
                is_co_executor=record.is_co_executor,
                stage=record.state,
                stage_changed_on=record.state_changed_on,
                step=step.value if step else None,
                deviation=deviation,
                sign_of_life=LifeRef(on=life.on, source=life.source.value) if life else None,
                has_problem=record.problem is not None,
                question=(
                    QuestionRef(
                        id=question.id,
                        text=question.text,
                        asked_on=local_date(question.created_at, zone),
                    )
                    if question
                    else None
                ),
                last_decision=(
                    DecisionRef(
                        id=decision.id,
                        kind=decision.kind,
                        decided_on=local_date(decision.created_at, zone),
                    )
                    if decision
                    else None
                ),
                tasks=record.tasks,
                first_seen_on=record.first_seen_on,
                version=record.version,
            )
        )
    return _Snapshot(
        records=records,
        lines=lines,
        rows=rows,
        documents=documents,
        people=people,
        organizations=organizations,
    )


# ---------------------------------------------------------------------------
# Ответы и стена
# ---------------------------------------------------------------------------


def _effect(batch: BatchRecord | None) -> BatchEffect | None:
    """Что изменила последняя применённая таблица — из отчёта партии (ТЗ 7)."""
    if batch is None:
        return None
    report = batch.report

    def ids(key: str) -> tuple[uuid.UUID, ...]:
        values = report.get(key)
        return tuple(uuid.UUID(str(value)) for value in values) if isinstance(values, list) else ()

    pending = report.get("pending")
    return BatchEffect(
        batch_id=batch.id,
        created=ids("created"),
        changed=ids("changed"),
        vanished=int(report.get("vanished", 0) or 0),
        pending_extensions=len(pending) if isinstance(pending, list) else 0,
    )


def _answer_view(answer: Answer, snapshot: _Snapshot, batch: BatchRecord | None) -> dict[str, Any]:
    """Ответ в форме экрана (`QuestionAnswer` в `model.ts`)."""

    def person(person_id: uuid.UUID | None) -> PersonRef | None:
        if person_id is None or person_id not in snapshot.people:
            return None
        return PersonRef(id=person_id, name=snapshot.people[person_id])

    def oldest() -> dict[str, Any] | None:
        return {"id": answer.oldest.id, "days": answer.oldest.days} if answer.oldest else None

    base: dict[str, Any] = {"key": answer.key.value, "rows": list(answer.rows)}
    match answer.key:
        case Question.BURNING:
            return base | {
                "burning": answer.burning,
                "overdue": answer.overdue,
                "oldest": oldest(),
                "by_person": [
                    {
                        "person": person(each.person_id),
                        "responsible_raw": each.responsible_raw,
                        "overdue": each.overdue,
                        "burning": each.burning,
                    }
                    for each in answer.by_person
                ],
            }
        case Question.FOREIGN:
            groups = []
            for group in answer.organizations:
                found = snapshot.organizations.get(group.organization_id)
                if found is None:
                    continue
                groups.append(
                    {
                        "organization": OrganizationRef(
                            id=found.id, name=found.name, short_name=found.short_name
                        ),
                        "count": group.count,
                        "rows": list(group.rows),
                    }
                )
            return base | {"count": answer.count, "organizations": groups}
        case Question.SILENT:
            worst = answer.silent_worst
            return base | {
                "count": answer.count,
                "worst": (
                    {
                        "id": worst.id,
                        "person": person(worst.person_id),
                        "responsible_raw": worst.responsible_raw,
                        "days": worst.days,
                    }
                    if worst
                    else None
                ),
            }
        case Question.DOCUMENTS:
            share = answer.document_worst
            return base | {
                "worst": (
                    {
                        "document": _document_ref(snapshot.documents[share.document_id]),
                        "done": share.done,
                        "total": share.total,
                    }
                    if share
                    else None
                )
            }
        case Question.CHRONIC:
            sample = answer.chronic_sample
            return base | {
                "count": answer.count,
                "sample": (
                    {
                        "id": sample.id,
                        "original_due_on": sample.original_due_on,
                        "due_on": sample.due_on,
                        "extensions": sample.extensions,
                    }
                    if sample
                    else None
                ),
            }
        case Question.YEAR_END:
            return base | {
                "upcoming": answer.upcoming,
                "closed": answer.closed,
                "window_days": answer.window_days,
                "min_closed": answer.min_closed,
                "verdict": answer.verdict.value if answer.verdict else None,
            }
        case Question.REPORT_UP:
            return base | {"count": answer.count, "freshest_on": answer.freshest_on}
        case Question.AWAITING | Question.RETURNED:
            return base | {"count": answer.count, "oldest": oldest()}
        case Question.EXTENSION_REQUESTED:
            return base | {"count": answer.count}
        case Question.WITHOUT_TASKS:
            return base | {"count": answer.count, "total": answer.total}
        case Question.LAST_BATCH:
            effect = answer.batch
            return base | {
                "batch": (
                    {
                        "id": batch.id,
                        "table_on": batch.table_on,
                        "file": batch.file,
                        "source": batch.source,
                    }
                    if batch and effect
                    else None
                ),
                "created": len(effect.created) if effect else 0,
                "changed": len(effect.changed) if effect else 0,
                "vanished": effect.vanished if effect else 0,
                "pending_extensions": effect.pending_extensions if effect else 0,
            }
    raise AssertionError(f"вопрос без формы ответа: {answer.key}")


def _wall_view(snapshot: _Snapshot) -> tuple[list[WallView], list[rules.WallDocument]]:
    present = [
        document_id
        for document_id in snapshot.documents
        if any(record.document_id == document_id for record in snapshot.records)
    ]
    walls = metrics.ijro_wall(
        snapshot.lines,
        present,
        {record.id: record.band for record in snapshot.records},
        {record.id: record.band_sort for record in snapshot.records},
    )
    views = []
    for wall in walls:
        call = wall.call_for_report
        views.append(
            WallView(
                document=_document_ref(snapshot.documents[wall.document_id]),
                done=wall.done,
                total=wall.total,
                cells=[
                    WallCellView(
                        id=cell.id,
                        band=cell.band,
                        stage=cell.state.value,
                        step=cell.step.value if cell.step else None,
                    )
                    for cell in wall.cells
                ],
                call_for_report=(
                    CallView(
                        person=PersonRef(id=call[0], name=snapshot.people[call[0]]), open=call[1]
                    )
                    if call and call[0] in snapshot.people
                    else None
                ),
            )
        )
    return views, walls


def _batch_view(batch: BatchRecord) -> BatchView:
    return BatchView(
        id=batch.id,
        file=batch.file,
        source=batch.source,
        table_on=batch.table_on,
        uploaded_at=batch.uploaded_at,
        state=batch.state,
        counts={name: batch.counts.get(name, 0) for name in CHANGE_CLASSES},
    )


async def load(session: AsyncSession, *, now: datetime, zone: ZoneInfo, is_demo: bool) -> IjroView:
    """Раздел целиком: вопросы, реестр в порядке лестницы, стена, история загрузок."""
    today = local_date(now, zone)
    thresholds = await metrics.load_thresholds(session)
    snapshot = await _snapshot(session, today=today, zone=zone, thresholds=thresholds)
    walls, wall_rules = _wall_view(snapshot)
    history = await read_model.batches(session, zone=zone)
    last = next((batch for batch in history if batch.state == ImportState.APPLIED.value), None)
    found = metrics.ijro_answers(
        snapshot.lines,
        today=today,
        thresholds=thresholds,
        documents=wall_rules,
        batch=_effect(last),
    )
    limits = metrics.ijro_limits(thresholds)
    responsible = {r.responsible_person_id for r in snapshot.records if r.responsible_person_id}
    return IjroView(
        as_of=now,
        table_on=last.table_on if last else None,
        thresholds=ThresholdsView(
            burn_days=thresholds.burn_days,
            quiet_days=thresholds.quiet_days,
            near_due_days=limits.near_due_days,
            pace_window_days=limits.pace_window_days,
            min_closed_for_pace=limits.min_closed_for_pace,
        ),
        questions=[_answer_view(answer, snapshot, last) for answer in found],
        items=snapshot.rows,
        documents=walls,
        people=[
            PersonRef(id=person_id, name=name)
            for person_id, name in snapshot.people.items()
            if person_id in responsible
        ],
        organizations=sorted(
            (
                OrganizationRef(id=org.id, name=org.name, short_name=org.short_name)
                for org in snapshot.organizations.values()
            ),
            key=lambda org: (org.short_name or org.name, str(org.id)),
        ),
        batches=[_batch_view(batch) for batch in history],
        is_demo=is_demo,
    )


async def card(
    session: AsyncSession, *, assignment_id: uuid.UUID, now: datetime, zone: ZoneInfo
) -> CardView:
    """Карточка поручения (ТЗ 3.3)."""
    today = local_date(now, zone)
    thresholds = await metrics.load_thresholds(session)
    snapshot = await _snapshot(
        session, today=today, zone=zone, thresholds=thresholds, ids=[assignment_id]
    )
    if not snapshot.records:
        raise NotFoundError("Поручение не найдено: его могли удалить")
    record, row = snapshot.records[0], snapshot.rows[0]

    # Ступень связанной задачи — с Пульта: расхождение «поручение горит, а задача идёт по
    # плану» видно только если ступень задачи посчитана тем же правилом (ADR-0033).
    ladder = await metrics.ladder(session, today=today, zone=zone, thresholds=thresholds)
    task_steps = {r.entity_id: r.attention.value for r in ladder.rows if r.section == "tasks"}

    batch_ref = ImportRef(batch_id=None, table_on=record.first_seen_on, file="")
    if record.import_batch_id is not None:
        for batch in await read_model.batches(session, zone=zone):
            if batch.id == record.import_batch_id:
                batch_ref = ImportRef(batch_id=batch.id, table_on=batch.table_on, file=batch.file)
                break

    suggestions = (
        [
            PersonRef(id=person_id, name=snapshot.people[person_id])
            for person_id in rules.suggest_people(
                split_responsible(record.responsible_raw)[0],
                list(snapshot.people.items()),
            )
        ]
        if record.responsible_person_id is None and record.responsible_raw
        else []
    )
    return CardView(
        row=row,
        document=_document_ref(snapshot.documents[record.document_id]),
        mechanism=record.mechanism,
        extension_history=[
            {
                "from": each.due_from,
                "to": each.due_to,
                "on": each.on,
                "batch_id": each.batch_id,
                "kind": each.kind,
            }
            for each in await read_model.extension_history(session, assignment_id, zone=zone)
        ],
        problem=record.problem,
        proposal=record.proposal,
        problem_updated_on=record.problem_updated_on,
        marks=[
            MarkView(
                id=mark.id,
                kind=mark.kind,
                promised_on=mark.promised_on,
                comment=mark.comment,
                made_at=mark.made_at,
                author=mark.author,
            )
            for mark in await read_model.marks(session, assignment_id)
        ],
        linked_tasks=[
            LinkedTaskView(
                id=task.id,
                code=task.code,
                title=task.title,
                status=task.status,
                step=task_steps.get(task.id),
                due_on=local_date(task.due_at, zone) if task.due_at else None,
                moved_on=local_date(task.moved_at, zone),
            )
            for task in await read_model.linked_tasks(session, assignment_id)
        ],
        comments=[
            CommentView(
                id=comment.id,
                text=comment.text,
                author=comment.author,
                created_at=comment.created_at,
            )
            for comment in await read_model.comments(session, assignment_id)
        ],
        suggestions=suggestions,
        import_=batch_ref,
    )


async def spravka(session: AsyncSession, *, now: datetime, zone: ZoneInfo) -> list[SpravkaLine]:
    """«Что докладывать наверх?» — открытые с записанной проблемой, в порядке лестницы."""
    today = local_date(now, zone)
    thresholds = await metrics.load_thresholds(session)
    snapshot = await _snapshot(session, today=today, zone=zone, thresholds=thresholds)
    lines: list[SpravkaLine] = []
    for record, row in zip(snapshot.records, snapshot.rows, strict=True):
        if not record.is_open or record.problem is None:
            continue
        lines.append(
            SpravkaLine(
                id=record.id,
                place=_place(row.document.code, record.band),
                content=record.content,
                due_on=record.due_on,
                due_precision=record.due_precision.value,
                responsible=row.responsible.name if row.responsible else record.responsible_raw,
                problem=record.problem,
                proposal=record.proposal,
                problem_updated_on=record.problem_updated_on,
            )
        )
    return lines


# ---------------------------------------------------------------------------
# Правки
# ---------------------------------------------------------------------------


async def _assignment(session: AsyncSession, assignment_id: uuid.UUID) -> IjroAssignment:
    found = await session.get(IjroAssignment, assignment_id)
    if found is None:
        raise NotFoundError("Поручение не найдено: его могли удалить")
    return found


async def mark(
    session: AsyncSession,
    *,
    user: User,
    assignment_id: uuid.UUID,
    kind: MarkKind,
    promised_on: date | None,
    comment: str | None,
    now: datetime,
    zone: ZoneInfo,
) -> uuid.UUID:
    """Контрольная отметка — оба пользователя (V35); она же признак жизни (ТЗ 4).

    Отметка — новая запись, а не правка поручения: версия поручения не нужна, и отметка с
    телефона руководителя не получит отказа из-за того, что помощник в ту же минуту
    поправил этап.
    """
    await _assignment(session, assignment_id)
    promised, text = rules.clean_mark(
        promised_on=promised_on, comment=comment, today=local_date(now, zone)
    )
    record = IjroControlMark(
        assignment_id=assignment_id,
        kind=kind.value,
        promised_on=promised,
        comment=text,
        author_id=user.id,
    )
    session.add(record)
    await session.flush()
    return record.id


async def set_stage(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    stage: IjroState,
    version: int,
    now: datetime,
) -> None:
    """Этап (ТЗ 3.3, V32). Тот же этап повторно — не правка: дата смены не сдвигается."""
    assignment = await _assignment(session, assignment_id)
    check_version(expected=version, actual=assignment.version)
    if assignment.state == stage.value:
        return
    assignment.state = stage.value
    assignment.state_changed_at = now


async def set_problem(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    problem: str | None,
    proposal: str | None,
    version: int,
    now: datetime,
) -> None:
    """Проблема и предложение — строка справки «что докладывать наверх» (ТЗ 3.3, 10)."""
    assignment = await _assignment(session, assignment_id)
    check_version(expected=version, actual=assignment.version)
    cleaned, offered = rules.clean_problem(problem, proposal)
    assignment.problem = cleaned
    assignment.proposal = offered
    assignment.problem_updated_at = now if cleaned is not None else None


async def set_extension_requested(
    session: AsyncSession, *, assignment_id: uuid.UUID, value: bool, version: int
) -> None:
    """«Запрошено продление» — помощник отправил запрос наверх (ТЗ 3.3)."""
    assignment = await _assignment(session, assignment_id)
    check_version(expected=version, actual=assignment.version)
    assignment.extension_requested = value


async def match_person(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    person_id: uuid.UUID,
    version: int,
) -> None:
    """Написание из таблицы → сотрудник. Подтверждает человек, псевдоним запоминается (ТЗ 7).

    Псевдоним ставит сотрудника и всем остальным несопоставленным строкам с тем же
    написанием: двадцать нажатий при первом привозе — и дальше система узнаёт написание
    сама ([ADR-0025](../../../docs/adr/ADR-0025-ijro-standalone-register.md)).
    """
    assignment = await _assignment(session, assignment_id)
    check_version(expected=version, actual=assignment.version)
    person = await session.get(Person, person_id)
    if person is None or not person.is_active:
        raise RuleViolationError("Сотрудник не найден в справочнике")
    raw = split_responsible(assignment.responsible_raw or "")[0]
    key = normalize_person_name(raw)
    if not key:
        raise RuleViolationError("У поручения нет написания ответственного из таблицы")

    alias = await session.scalar(select(IjroPersonAlias).where(IjroPersonAlias.alias_norm == key))
    if alias is None:
        session.add(
            IjroPersonAlias(alias_norm=key, person_id=person_id, source=AliasSource.MANUAL.value)
        )
    else:
        alias.person_id = person_id
        alias.source = AliasSource.MANUAL.value

    assignment.responsible_person_id = person_id
    others = await session.scalars(
        select(IjroAssignment).where(
            IjroAssignment.responsible_person_id.is_(None), IjroAssignment.id != assignment_id
        )
    )
    for other in others:
        if normalize_person_name(split_responsible(other.responsible_raw or "")[0]) == key:
            other.responsible_person_id = person_id


async def comment(
    session: AsyncSession, *, user: User, assignment_id: uuid.UUID, text: str
) -> uuid.UUID:
    """Реплика в ленте хода исполнения — оба пользователя (`app.domain.comments`)."""
    await _assignment(session, assignment_id)
    try:
        body = validate_body(text)
    except ValueError as error:
        raise RuleViolationError("Комментарий не сохранён", detail=str(error)) from error
    record = Comment(
        entity_type=CommentTarget.IJRO_ASSIGNMENT.value,
        entity_id=assignment_id,
        author_id=user.id,
        body=body,
    )
    session.add(record)
    await session.flush()
    return record.id


async def task_prefill(session: AsyncSession, *, assignment_id: uuid.UUID) -> TaskPrefill:
    """«Разложить на задачу» (ADR-0033, V34): что покажет лист подтверждения."""
    assignment = await _assignment(session, assignment_id)
    return TaskPrefill(
        title=rules.task_title(assignment.content),
        type_code=TASK_TYPE,
        assignee_id=assignment.responsible_person_id,
        due_on=rules.task_due(assignment.due_on, DuePrecision(assignment.due_precision)),
        ijro_assignment_id=assignment.id,
    )


async def create_task(
    session: AsyncSession,
    *,
    user: User,
    assignment_id: uuid.UUID,
    now: datetime,
    zone: ZoneInfo,
) -> CreatedTask:
    """Задача из поручения — тем же `tasks.create`, что строка «Новая задача»: один вход."""
    prefill = await task_prefill(session, assignment_id=assignment_id)
    task_id = await tasks.create(
        session,
        user=user,
        data=tasks.NewTask(
            title=prefill.title,
            type_code=prefill.type_code,
            due_on=prefill.due_on,
            assignee_id=prefill.assignee_id,
            project_id=None,
            ijro_assignment_id=assignment_id,
        ),
        now=now,
        zone=zone,
    )
    found = await read_model.linked_tasks(session, assignment_id)
    code = next(task.code for task in found if task.id == task_id)
    return CreatedTask(id=task_id, code=code)
