"""Read-модель раздела «Ижро»: реестр, карточка, партии привоза.

Реестр собирается фиксированным числом запросов — строки, отметки, задачи, продления — а
не обходом по поручению (CLAUDE.md, «Read-модель на экран»): таблица на 165 строк не имеет
права стоить 165 обращений к базе.

Отсюда же берёт строки лестница Пульта (`app.repos.attention`): признак жизни и перевод в
`Item` — одна функция на оба экрана, иначе поручение могло бы гореть на Пульте и идти по
плану в своём разделе (инвариант 2).

**Даты — по Ташкенту** (инвариант 8): моменты из базы переводятся `local_date`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import Item
from app.domain.clock import local_date
from app.domain.comments import CommentTarget
from app.domain.ijro import (
    OPEN_STATES,
    DuePrecision,
    ExtensionKind,
    IjroState,
    ImportState,
    LifeSource,
)
from app.domain.ijro_control import LifeSign, sign_of_life
from app.domain.ijro_import import Existing
from app.repos.models import (
    Comment,
    IjroAssignment,
    IjroControlMark,
    IjroDocument,
    IjroExtension,
    IjroImport,
    IjroOrgAlias,
    IjroPersonAlias,
    Organization,
    Person,
    Task,
    TaskChecklistItem,
    User,
)

SECTION = "ijro"
"""Раздел строки лестницы — как у экрана Пульта (`RowSection`)."""


@dataclass(frozen=True, slots=True)
class AssignmentRecord:
    """Строка реестра со всем, что нужно списку, лестнице и вопросам."""

    id: uuid.UUID
    document_id: uuid.UUID
    band: str | None
    band_sort: str
    content: str
    mechanism: str | None
    due_on: date | None
    due_precision: DuePrecision
    original_due_on: date | None
    extension_requested: bool
    responsible_raw: str
    responsible_person_id: uuid.UUID | None
    lead_organization_id: uuid.UUID | None
    is_co_executor: bool
    state: str
    state_changed_on: date
    first_seen_on: date
    problem: str | None
    proposal: str | None
    problem_updated_on: date | None
    import_batch_id: uuid.UUID | None
    version: int
    last_mark_on: date | None
    last_task_move_on: date | None
    tasks: int
    extensions: int
    """Продления — без исправленных дат: «продлевали ≥ 2» про них (ТЗ 5)."""

    @property
    def is_open(self) -> bool:
        return self.state in {state.value for state in OPEN_STATES}

    @property
    def life(self) -> LifeSign | None:
        """Признак жизни: самое свежее из отметки и движения задачи (ТЗ 4).

        Третье событие ТЗ — «промежуточная информация» — пока не записывается нигде: у неё
        нет ни поля, ни действия на утверждённом экране (вопрос V37). Когда появится, оно
        встанет третьим в этот список, и лестница подхватит его без правки.
        """
        events = []
        if self.last_mark_on is not None:
            events.append(LifeSign(self.last_mark_on, LifeSource.CONTROL_MARK))
        if self.last_task_move_on is not None:
            events.append(LifeSign(self.last_task_move_on, LifeSource.TASK_MOVEMENT))
        return sign_of_life(events)


def item_of(record: AssignmentRecord, awaiting_since: date | None) -> Item:
    """Строка лестницы из поручения — одна на Пульт и раздел.

    Тишина без единого события считается от появления строки в реестре: иначе поручение,
    по которому с привоза ничего не происходило, никогда бы не «молчало».
    """
    life = record.life
    return Item(
        section=SECTION,
        entity_id=record.id,
        title=record.content,
        due_on=record.due_on,
        last_sign_of_life=life.on if life else record.first_seen_on,
        awaiting_since=awaiting_since,
        lead_is_outside=record.is_co_executor,
        responsible_person_id=record.responsible_person_id,
        due_is_exact=record.due_precision is DuePrecision.EXACT,
    )


def _task_moves() -> Any:
    """Последнее движение задач по поручению и их число — как у задачи на Пульте.

    Отметка пункта чек-листа — движение задачи (`app.repos.attention._tasks`), а значит, и
    признак жизни поручения.
    """
    latest_item = (
        select(
            TaskChecklistItem.task_id,
            func.max(
                func.coalesce(TaskChecklistItem.updated_at, TaskChecklistItem.created_at)
            ).label("moved"),
        )
        .group_by(TaskChecklistItem.task_id)
        .subquery()
    )
    return (
        select(
            Task.ijro_assignment_id.label("assignment_id"),
            func.max(
                func.greatest(func.coalesce(Task.updated_at, Task.created_at), latest_item.c.moved)
            ).label("moved"),
            func.count(Task.id).label("tasks"),
        )
        .outerjoin(latest_item, latest_item.c.task_id == Task.id)
        .where(Task.ijro_assignment_id.is_not(None))
        .group_by(Task.ijro_assignment_id)
        .subquery()
    )


async def records(
    session: AsyncSession,
    *,
    zone: ZoneInfo,
    open_only: bool = False,
    ids: list[uuid.UUID] | None = None,
) -> list[AssignmentRecord]:
    """Строки реестра. `open_only` — только этапы, на которых работа наша (лестница)."""
    marks = (
        select(
            IjroControlMark.assignment_id,
            func.max(IjroControlMark.created_at).label("marked"),
        )
        .group_by(IjroControlMark.assignment_id)
        .subquery()
    )
    extensions = (
        select(IjroExtension.assignment_id, func.count(IjroExtension.id).label("count"))
        .where(IjroExtension.kind == ExtensionKind.EXTENSION.value)
        .group_by(IjroExtension.assignment_id)
        .subquery()
    )
    moves = _task_moves()
    statement = (
        select(IjroAssignment, marks.c.marked, moves.c.moved, moves.c.tasks, extensions.c.count)
        .outerjoin(marks, marks.c.assignment_id == IjroAssignment.id)
        .outerjoin(moves, moves.c.assignment_id == IjroAssignment.id)
        .outerjoin(extensions, extensions.c.assignment_id == IjroAssignment.id)
    )
    if open_only:
        statement = statement.where(
            IjroAssignment.state.in_([state.value for state in OPEN_STATES])
        )
    if ids is not None:
        statement = statement.where(IjroAssignment.id.in_(ids))
    rows = await session.execute(statement)

    def day(moment: datetime | None) -> date | None:
        return local_date(moment, zone) if moment is not None else None

    found: list[AssignmentRecord] = []
    for assignment, marked, moved, tasks, extension_count in rows:
        first_seen = local_date(assignment.first_seen_at or assignment.created_at, zone)
        found.append(
            AssignmentRecord(
                id=assignment.id,
                document_id=assignment.document_id,
                band=assignment.band,
                band_sort=assignment.band_sort or "",
                content=assignment.content,
                mechanism=assignment.mechanism,
                due_on=assignment.due_on,
                due_precision=DuePrecision(assignment.due_precision),
                original_due_on=assignment.original_due_on or assignment.due_on,
                extension_requested=assignment.extension_requested,
                responsible_raw=assignment.responsible_raw or "",
                responsible_person_id=assignment.responsible_person_id,
                lead_organization_id=assignment.lead_organization_id,
                is_co_executor=assignment.is_co_executor,
                state=assignment.state,
                state_changed_on=day(assignment.state_changed_at) or first_seen,
                first_seen_on=first_seen,
                problem=assignment.problem,
                proposal=assignment.proposal,
                problem_updated_on=day(assignment.problem_updated_at),
                import_batch_id=assignment.import_batch_id,
                version=assignment.version,
                last_mark_on=day(marked),
                last_task_move_on=day(moved),
                tasks=tasks or 0,
                extensions=extension_count or 0,
            )
        )
    return found


# ---------------------------------------------------------------------------
# Справочные строки экрана: документы, люди, ведомства, партии
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    id: uuid.UUID
    kind: str
    code: str
    issued_on: date | None
    title: str
    source: str


async def documents(session: AsyncSession) -> list[DocumentRecord]:
    """Документы от старых к новым — порядок карточек стены: старый документ дольше на контроле."""
    rows = await session.scalars(
        select(IjroDocument).order_by(
            IjroDocument.issued_on.asc().nulls_last(), IjroDocument.number_raw
        )
    )
    return [
        DocumentRecord(
            id=document.id,
            kind=document.kind,
            code=document.number_raw,
            issued_on=document.issued_on,
            title=document.title_raw or "",
            source=document.source,
        )
        for document in rows
    ]


async def people(session: AsyncSession) -> list[tuple[uuid.UUID, str]]:
    """Действующие сотрудники — для предложения «Это Каримов А.?» и подписи строк."""
    rows = await session.execute(
        select(Person.id, Person.full_name)
        .where(Person.is_active.is_(True))
        .order_by(Person.full_name, Person.id)
    )
    return list(rows.tuples())


@dataclass(frozen=True, slots=True)
class OrganizationRecord:
    id: uuid.UUID
    name: str
    short_name: str | None


async def organizations(
    session: AsyncSession, ids: set[uuid.UUID]
) -> dict[uuid.UUID, OrganizationRecord]:
    if not ids:
        return {}
    rows = await session.execute(
        select(Organization.id, Organization.name, Organization.short_name).where(
            Organization.id.in_(ids)
        )
    )
    return {
        org_id: OrganizationRecord(id=org_id, name=name, short_name=short)
        for org_id, name, short in rows
    }


@dataclass(frozen=True, slots=True)
class BatchRecord:
    id: uuid.UUID
    file: str
    source: str | None
    table_on: date
    uploaded_at: datetime
    state: str
    applied_at: datetime | None
    counts: dict[str, int]
    report: dict[str, Any]


async def batches(session: AsyncSession, *, zone: ZoneInfo) -> list[BatchRecord]:
    """Применённые и отвергнутые партии — новые первыми. Предпросмотр в истории не стоит."""
    rows = await session.scalars(
        select(IjroImport)
        .where(IjroImport.state != ImportState.PREVIEW.value)
        .order_by(IjroImport.uploaded_at.desc().nulls_last(), IjroImport.created_at.desc())
    )
    found: list[BatchRecord] = []
    for batch in rows:
        uploaded = batch.uploaded_at or batch.created_at
        report: dict[str, Any] = dict(batch.report or {})
        stored = report.get("counts")
        counts = (
            {str(key): int(value) for key, value in stored.items()}
            if isinstance(stored, dict)
            else {
                "new": batch.rows_new,
                "text_changed": batch.rows_changed,
                "unrecognized": batch.rows_unrecognized,
            }
        )
        found.append(
            BatchRecord(
                id=batch.id,
                file=batch.filename,
                source=batch.source,
                table_on=batch.table_on or local_date(uploaded, zone),
                uploaded_at=uploaded,
                state=batch.state,
                applied_at=batch.applied_at,
                counts=counts,
                report=report,
            )
        )
    return found


# ---------------------------------------------------------------------------
# Карточка
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MarkRecord:
    id: uuid.UUID
    kind: str
    promised_on: date | None
    comment: str | None
    made_at: datetime
    author: str | None


async def marks(session: AsyncSession, assignment_id: uuid.UUID) -> list[MarkRecord]:
    """Контрольные отметки — новые первыми, с ролью автора (инвариант 13)."""
    rows = await session.execute(
        select(IjroControlMark, User.role)
        .outerjoin(User, User.id == IjroControlMark.author_id)
        .where(IjroControlMark.assignment_id == assignment_id)
        .order_by(IjroControlMark.created_at.desc(), IjroControlMark.id)
    )
    return [
        MarkRecord(
            id=mark.id,
            kind=mark.kind,
            promised_on=mark.promised_on,
            comment=mark.comment,
            made_at=mark.created_at,
            author=role,
        )
        for mark, role in rows
    ]


@dataclass(frozen=True, slots=True)
class LinkedTaskRecord:
    id: uuid.UUID
    code: str
    title: str
    status: str
    due_at: datetime | None
    moved_at: datetime


async def linked_tasks(session: AsyncSession, assignment_id: uuid.UUID) -> list[LinkedTaskRecord]:
    rows = await session.execute(
        select(
            Task.id,
            Task.code,
            Task.title,
            Task.status,
            Task.due_at,
            func.coalesce(Task.updated_at, Task.created_at),
        )
        .where(Task.ijro_assignment_id == assignment_id)
        .order_by(Task.created_at, Task.id)
    )
    return [
        LinkedTaskRecord(
            id=task_id, code=code, title=title, status=status, due_at=due_at, moved_at=moved
        )
        for task_id, code, title, status, due_at, moved in rows
    ]


@dataclass(frozen=True, slots=True)
class CommentRecord:
    id: uuid.UUID
    text: str
    author: str | None
    created_at: datetime


async def comments(session: AsyncSession, assignment_id: uuid.UUID) -> list[CommentRecord]:
    """Лента — по порядку; удалённая реплика в ленту не выдаётся (`app.domain.comments`)."""
    rows = await session.execute(
        select(Comment, User.role)
        .outerjoin(User, User.id == Comment.author_id)
        .where(
            Comment.entity_type == CommentTarget.IJRO_ASSIGNMENT.value,
            Comment.entity_id == assignment_id,
            Comment.deleted_at.is_(None),
        )
        .order_by(Comment.created_at, Comment.id)
    )
    return [
        CommentRecord(id=comment.id, text=comment.body, author=role, created_at=comment.created_at)
        for comment, role in rows
    ]


@dataclass(frozen=True, slots=True)
class ExtensionRecord:
    due_from: date
    due_to: date
    on: date
    batch_id: uuid.UUID | None
    kind: str


async def extension_history(
    session: AsyncSession, assignment_id: uuid.UUID, *, zone: ZoneInfo
) -> list[ExtensionRecord]:
    """История продлений по порядку. Дата — дата таблицы, из которой пришёл перенос."""
    rows = await session.execute(
        select(IjroExtension, IjroImport.table_on)
        .outerjoin(IjroImport, IjroImport.id == IjroExtension.import_batch_id)
        .where(IjroExtension.assignment_id == assignment_id)
        .order_by(IjroExtension.created_at, IjroExtension.id)
    )
    return [
        ExtensionRecord(
            due_from=extension.due_from,
            due_to=extension.due_to,
            on=table_on or local_date(extension.created_at, zone),
            batch_id=extension.import_batch_id,
            kind=extension.kind,
        )
        for extension, table_on in rows
    ]


# ---------------------------------------------------------------------------
# Привоз таблицы
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegistryRow:
    """Строка реестра для сверки с таблицей: поля источника и сопоставленный сотрудник."""

    existing: Existing
    document_code: str
    responsible_person_id: uuid.UUID | None


async def import_registry(session: AsyncSession) -> list[RegistryRow]:
    """Весь реестр одним запросом — с ключом повтора (документ, пункт, срок)."""
    rows = await session.execute(
        select(
            IjroAssignment.id,
            IjroDocument.code_norm,
            IjroDocument.number_raw,
            IjroDocument.source,
            IjroAssignment.band,
            IjroAssignment.due_on,
            IjroAssignment.content,
            IjroAssignment.mechanism,
            IjroAssignment.responsible_raw,
            IjroAssignment.responsible_person_id,
            IjroAssignment.state,
        ).join(IjroDocument, IjroDocument.id == IjroAssignment.document_id)
    )
    return [
        RegistryRow(
            existing=Existing(
                id=assignment_id,
                code_norm=code_norm,
                band=band,
                due_on=due_on,
                content=content,
                mechanism=mechanism,
                responsible_raw=responsible_raw or "",
                source=source,
                removed=state == IjroState.REMOVED_FROM_CONTROL.value,
            ),
            document_code=number_raw,
            responsible_person_id=person_id,
        )
        for (
            assignment_id,
            code_norm,
            number_raw,
            source,
            band,
            due_on,
            content,
            mechanism,
            responsible_raw,
            person_id,
            state,
        ) in rows
    ]


async def person_aliases(session: AsyncSession) -> dict[str, uuid.UUID]:
    rows = await session.execute(select(IjroPersonAlias.alias_norm, IjroPersonAlias.person_id))
    return dict(rows.tuples().all())


async def organization_keys(session: AsyncSession) -> list[tuple[uuid.UUID, str, str | None]]:
    """Ведомства справочника — имя и короткое имя — для сопоставления головного исполнителя."""
    rows = await session.execute(
        select(Organization.id, Organization.name, Organization.short_name)
    )
    return list(rows.tuples().all())


async def organization_aliases(session: AsyncSession) -> dict[str, uuid.UUID]:
    rows = await session.execute(select(IjroOrgAlias.alias_norm, IjroOrgAlias.organization_id))
    return dict(rows.tuples().all())


async def applied_import(session: AsyncSession, sha256: str) -> IjroImport | None:
    """Применённая партия с тем же файлом — повтор ничего не меняет (ТЗ 7)."""
    found: IjroImport | None = await session.scalar(
        select(IjroImport).where(
            IjroImport.sha256 == sha256, IjroImport.state == ImportState.APPLIED.value
        )
    )
    return found


async def document_by_code(session: AsyncSession, code_norm: str) -> IjroDocument | None:
    found: IjroDocument | None = await session.scalar(
        select(IjroDocument).where(IjroDocument.code_norm == code_norm)
    )
    return found
