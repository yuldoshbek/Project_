"""Read-модель раздела «Взаимодействие»: письма, соглашения, организации.

Раздел собирается фиксированным числом запросов — письма, соглашения, организации,
поручения и проекты организаций — а не обходом по записи (CLAUDE.md, «Read-модель на
экран»).

Отсюда же берёт строки лестница Пульта (`app.repos.attention`): перевод письма и
соглашения в `Item` — одна функция на оба экрана, иначе письмо могло бы гореть на Пульте и
идти по плану в своём разделе (инвариант 2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.attention import Item
from app.domain.clock import local_date
from app.domain.ijro import OPEN_STATES
from app.domain.interaction import Direction, LetterState, letter_state
from app.repos.models import (
    Agreement,
    IjroAssignment,
    IjroDocument,
    Letter,
    Organization,
    Person,
    Project,
    ProjectOrganization,
)

LETTERS = "letters"
AGREEMENTS = "agreements"
"""Разделы строк лестницы — как у экрана Пульта (`RowSection`)."""


@dataclass(frozen=True, slots=True)
class OrganizationRecord:
    id: uuid.UUID
    name: str
    short_name: str | None
    kind: str
    is_founded_by_agency: bool
    phone: str | None
    email: str | None


@dataclass(frozen=True, slots=True)
class LetterRecord:
    id: uuid.UUID
    direction: Direction
    organization_id: uuid.UUID
    subject: str
    number: str | None
    sent_on: date
    due_on: date | None
    author_id: uuid.UUID | None
    author_name: str | None
    link: tuple[str, uuid.UUID, str] | None
    """Вид связи, запись и её название: проект или поручение Ижро."""

    answered_on: date | None
    reply_number: str | None
    rating: str | None
    version: int

    @property
    def state(self) -> LetterState:
        return letter_state(self.direction, self.answered_on)


@dataclass(frozen=True, slots=True)
class AgreementRecord:
    id: uuid.UUID
    organization_id: uuid.UUID
    kind: str
    title: str
    signed_on: date
    valid_until: date | None
    next_step: str | None
    next_step_on: date | None
    responsible_id: uuid.UUID | None
    responsible_name: str | None
    moved_on: date
    version: int


def letter_item(record: LetterRecord, awaiting_since: date | None) -> Item | None:
    """Строка лестницы из письма — одна на Пульт и раздел; отвеченное в лестницу не входит.

    Входящее горит и просрочивается своим сроком, как задача. Наше исходящее ждёт чужих
    (V39): с попрошенным сроком — как только он прошёл (`due_is_others`), без срока — после
    порога молчания, считая от дня письма.
    """
    if record.answered_on is not None:
        return None
    outgoing = record.direction is Direction.OUTGOING
    return Item(
        section=LETTERS,
        entity_id=record.id,
        title=record.subject,
        due_on=record.due_on,
        last_sign_of_life=(record.due_on or record.sent_on) if outgoing else None,
        awaiting_since=awaiting_since,
        lead_is_outside=outgoing,
        responsible_person_id=record.author_id,
        due_is_others=outgoing,
    )


def agreement_item(
    record: AgreementRecord, awaiting_since: date | None, *, sleeping_days: int
) -> Item:
    """Строка лестницы из соглашения: следующий шаг — срок, правка шага — движение (V40)."""
    return Item(
        section=AGREEMENTS,
        entity_id=record.id,
        title=record.title,
        due_on=record.next_step_on,
        last_sign_of_life=record.moved_on,
        awaiting_since=awaiting_since,
        lead_is_outside=False,
        responsible_person_id=record.responsible_id,
        quiet_days=sleeping_days,
    )


async def letters(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    unanswered_only: bool = False,
    ids: list[uuid.UUID] | None = None,
) -> list[LetterRecord]:
    author = aliased(Person)
    document = aliased(IjroDocument)
    statement = (
        select(
            Letter,
            author.full_name,
            Project.title,
            IjroAssignment.band,
            document.number_raw,
        )
        .outerjoin(author, author.id == Letter.author_person_id)
        .outerjoin(Project, Project.id == Letter.project_id)
        .outerjoin(IjroAssignment, IjroAssignment.id == Letter.ijro_assignment_id)
        .outerjoin(document, document.id == IjroAssignment.document_id)
    )
    if organization_id is not None:
        statement = statement.where(Letter.organization_id == organization_id)
    if unanswered_only:
        statement = statement.where(Letter.answered_on.is_(None))
    if ids is not None:
        statement = statement.where(Letter.id.in_(ids))
    rows = await session.execute(statement)
    found: list[LetterRecord] = []
    for letter, author_name, project_title, band, code in rows:
        link: tuple[str, uuid.UUID, str] | None = None
        if letter.project_id is not None and project_title is not None:
            link = ("project", letter.project_id, project_title)
        elif letter.ijro_assignment_id is not None and code is not None:
            link = ("ijro", letter.ijro_assignment_id, f"{code} · {band}" if band else code)
        found.append(
            LetterRecord(
                id=letter.id,
                direction=Direction(letter.direction),
                organization_id=letter.organization_id,
                subject=letter.subject,
                number=letter.number,
                sent_on=letter.sent_on,
                due_on=letter.due_on,
                author_id=letter.author_person_id,
                author_name=author_name,
                link=link,
                answered_on=letter.answered_on,
                reply_number=letter.reply_number,
                rating=letter.rating,
                version=letter.version,
            )
        )
    return found


async def agreements(
    session: AsyncSession, *, zone: ZoneInfo, organization_id: uuid.UUID | None = None
) -> list[AgreementRecord]:
    statement = select(Agreement, Person.full_name).outerjoin(
        Person, Person.id == Agreement.responsible_person_id
    )
    if organization_id is not None:
        statement = statement.where(Agreement.organization_id == organization_id)
    rows = await session.execute(statement)
    return [
        AgreementRecord(
            id=agreement.id,
            organization_id=agreement.organization_id,
            kind=agreement.kind,
            title=agreement.title,
            signed_on=agreement.signed_on,
            valid_until=agreement.valid_until,
            next_step=agreement.next_step,
            next_step_on=agreement.next_step_on,
            responsible_id=agreement.responsible_person_id,
            responsible_name=name,
            moved_on=local_date(agreement.moved_at, zone),
            version=agreement.version,
        )
        for agreement, name in rows
    ]


def _organization(organization: Organization) -> OrganizationRecord:
    return OrganizationRecord(
        id=organization.id,
        name=organization.name,
        short_name=organization.short_name,
        kind=organization.kind,
        is_founded_by_agency=organization.is_founded_by_agency,
        phone=organization.phone,
        email=organization.email,
    )


async def organizations(session: AsyncSession) -> list[OrganizationRecord]:
    """Организации, с которыми есть переписка или соглашения, — вкладка «Организации»."""
    with_letters = select(Letter.organization_id)
    with_agreements = select(Agreement.organization_id)
    rows = await session.scalars(
        select(Organization).where(
            or_(
                Organization.id.in_(with_letters),
                Organization.id.in_(with_agreements),
            )
        )
    )
    return [_organization(each) for each in rows]


async def organization(
    session: AsyncSession, organization_id: uuid.UUID
) -> OrganizationRecord | None:
    found = await session.get(Organization, organization_id)
    return _organization(found) if found is not None else None


async def choices(session: AsyncSession) -> list[tuple[uuid.UUID, str, str | None]]:
    """Все действующие организации — выбор в форме нового письма."""
    rows = await session.execute(
        select(Organization.id, Organization.name, Organization.short_name)
        .where(Organization.is_active.is_(True))
        .order_by(func.coalesce(Organization.short_name, Organization.name), Organization.id)
    )
    return list(rows.tuples())


async def ijro_lead(session: AsyncSession) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Открытые поручения Ижро по головному ведомству — «из-за кого сорвётся» в карточке."""
    rows = await session.execute(
        select(IjroAssignment.lead_organization_id, IjroAssignment.id).where(
            IjroAssignment.lead_organization_id.is_not(None),
            IjroAssignment.state.in_([state.value for state in OPEN_STATES]),
        )
    )
    found: dict[uuid.UUID, list[uuid.UUID]] = {}
    for org_id, assignment_id in rows:
        found.setdefault(org_id, []).append(assignment_id)
    return found


@dataclass(frozen=True, slots=True)
class ProjectRef:
    id: uuid.UUID
    code: str
    title: str
    role: str


async def projects(session: AsyncSession) -> dict[uuid.UUID, list[ProjectRef]]:
    """Проекты организаций с ролью организации в проекте (ТЗ 3.1)."""
    rows = await session.execute(
        select(
            ProjectOrganization.organization_id,
            Project.id,
            Project.code,
            Project.title,
            ProjectOrganization.role,
        )
        .join(Project, Project.id == ProjectOrganization.project_id)
        .order_by(Project.code)
    )
    found: dict[uuid.UUID, list[ProjectRef]] = {}
    for org_id, project_id, code, title, role in rows:
        found.setdefault(org_id, []).append(ProjectRef(project_id, code, title, role))
    return found


async def letter(session: AsyncSession, letter_id: uuid.UUID) -> Letter | None:
    found: Letter | None = await session.get(Letter, letter_id)
    return found


async def agreement(session: AsyncSession, agreement_id: uuid.UUID) -> Agreement | None:
    found: Agreement | None = await session.get(Agreement, agreement_id)
    return found
