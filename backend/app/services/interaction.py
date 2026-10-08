"""Взаимодействие — письма, организации, соглашения (ТЗ 3.4, 5).

Форма — договор экрана `frontend/src/sections/interaction/model.ts`, утверждённого
заказчиком 01.10.2026 на вымышленных данных той же формы (CLAUDE.md, цикл блока).

**Числа — из `app.services.metrics`** (инвариант 2): ступень письма и соглашения считает тот
же `build_ladder`, что строит Пульт; четыре ответа — `app.domain.interaction` через сервис
показателей. Здесь — сборка экрана и правки.

**Роль подписывает действие** (инвариант 13): письмо вносит и ответ отмечает помощник,
ответ оценивает руководитель (V38), следующий шаг соглашения — помощник. Проверка роли
стоит на входе (`app.api.routes.interaction`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import interaction as rules
from app.domain.attention import Attention, Item, sort_key
from app.domain.clock import local_date
from app.domain.decisions import DecisionTarget
from app.domain.errors import NotFoundError, RuleViolationError, check_version
from app.domain.interaction import Direction, LetterState, Question, Rating
from app.domain.projects import validate_horizon
from app.repos import ijro as ijro_model
from app.repos import interaction as read_model
from app.repos import pult as pult_model
from app.repos.interaction import AgreementRecord, LetterRecord, OrganizationRecord
from app.repos.models import Letter, Person
from app.services import metrics


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
class LetterView:
    id: uuid.UUID
    direction: str
    organization: OrganizationRef
    subject: str
    number: str | None
    sent_on: date
    due_on: date | None
    author: PersonRef | None
    link: dict[str, Any] | None
    answered_on: date | None
    reply: dict[str, Any] | None
    rating: str | None
    state: str
    step: str | None
    deviation: int
    days: int
    version: int


@dataclass(frozen=True, slots=True)
class AgreementView:
    id: uuid.UUID
    organization: OrganizationRef
    kind: str
    title: str
    signed_on: date
    valid_until: date | None
    next_step: str | None
    next_step_on: date | None
    responsible: PersonRef | None
    moved_on: date
    sleeping: bool
    quiet_days: int
    step: str | None
    deviation: int
    version: int


@dataclass(frozen=True, slots=True)
class OrganizationView:
    id: uuid.UUID
    name: str
    short_name: str | None
    kind: str
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
    speed: dict[str, int | None]
    ratings: dict[str, int]


@dataclass(frozen=True, slots=True)
class OrganizationCard:
    organization: OrganizationView
    letters: list[LetterView]
    agreements: list[AgreementView]
    ijro: list[dict[str, Any]]
    projects: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class InteractionView:
    as_of: datetime
    thresholds: dict[str, int]
    questions: list[dict[str, Any]]
    letters: list[LetterView]
    organizations: list[OrganizationView]
    agreements: list[AgreementView]
    people: list[PersonRef]
    choices: list[OrganizationRef]
    is_demo: bool


@dataclass(frozen=True, slots=True)
class NewLetter:
    direction: Direction
    organization_id: uuid.UUID
    subject: str
    number: str | None
    sent_on: date
    due_on: date | None
    author_id: uuid.UUID | None


# ---------------------------------------------------------------------------
# Снимок
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Snapshot:
    today: date
    thresholds: metrics.Thresholds
    letters: list[LetterView]
    letter_lines: list[rules.LetterLine]
    agreements: list[AgreementView]
    agreement_lines: list[rules.AgreementLine]
    organizations: dict[uuid.UUID, OrganizationRecord]


def _ref(organization: OrganizationRecord) -> OrganizationRef:
    return OrganizationRef(
        id=organization.id, name=organization.name, short_name=organization.short_name
    )


def _order(step: Attention | None, deviation: int) -> tuple[int, int]:
    rank, urgency, _ = sort_key(step or Attention.ON_TRACK, deviation, None)
    return rank, urgency


async def _snapshot(
    session: AsyncSession,
    *,
    today: date,
    zone: ZoneInfo,
    organization_id: uuid.UUID | None = None,
) -> _Snapshot:
    thresholds = await metrics.load_thresholds(session)
    letters = await read_model.letters(session, organization_id=organization_id)
    agreements = await read_model.agreements(session, zone=zone, organization_id=organization_id)
    organizations = {each.id: each for each in await read_model.organizations(session)}
    used = {each.organization_id for each in letters} | {
        each.organization_id for each in agreements
    }
    for org_id in used - set(organizations):
        found = await read_model.organization(session, org_id)
        if found is not None:
            organizations[org_id] = found

    targets = [(DecisionTarget.LETTER.value, each.id) for each in letters] + [
        (DecisionTarget.AGREEMENT.value, each.id) for each in agreements
    ]
    questions = await pult_model.open_questions(session, targets)

    def asked(kind: DecisionTarget, entity_id: uuid.UUID) -> date | None:
        question = questions.get((kind.value, entity_id))
        return local_date(question.created_at, zone) if question else None

    items: list[Item] = []
    for record in letters:
        item = read_model.letter_item(record, asked(DecisionTarget.LETTER, record.id))
        if item is not None:
            items.append(item)
    items += [
        read_model.agreement_item(
            record,
            asked(DecisionTarget.AGREEMENT, record.id),
            sleeping_days=thresholds.sleeping_days,
        )
        for record in agreements
    ]
    ladder = metrics.steps(items, today=today, thresholds=thresholds)

    def letter_view(record: LetterRecord) -> LetterView:
        row = ladder.get(record.id)
        org = organizations[record.organization_id]
        days = (
            (record.answered_on - record.sent_on).days
            if record.answered_on is not None
            else (today - record.sent_on).days
        )
        return LetterView(
            id=record.id,
            direction=record.direction.value,
            organization=_ref(org),
            subject=record.subject,
            number=record.number,
            sent_on=record.sent_on,
            due_on=record.due_on,
            author=(
                PersonRef(id=record.author_id, name=record.author_name)
                if record.author_id and record.author_name
                else None
            ),
            link=(
                {"type": record.link[0], "id": record.link[1], "title": record.link[2]}
                if record.link
                else None
            ),
            answered_on=record.answered_on,
            reply=(
                {"number": record.reply_number, "sent_on": record.answered_on}
                if record.answered_on is not None
                else None
            ),
            rating=record.rating,
            state=record.state.value,
            step=row.attention.value if row else None,
            deviation=row.deviation if row else 0,
            days=days,
            version=record.version,
        )

    def agreement_view(record: AgreementRecord) -> AgreementView:
        row = ladder.get(record.id)
        quiet = (today - record.moved_on).days
        return AgreementView(
            id=record.id,
            organization=_ref(organizations[record.organization_id]),
            kind=record.kind,
            title=record.title,
            signed_on=record.signed_on,
            valid_until=record.valid_until,
            next_step=record.next_step,
            next_step_on=record.next_step_on,
            responsible=(
                PersonRef(id=record.responsible_id, name=record.responsible_name)
                if record.responsible_id and record.responsible_name
                else None
            ),
            moved_on=record.moved_on,
            sleeping=quiet > thresholds.sleeping_days,
            quiet_days=quiet,
            step=row.attention.value if row else None,
            deviation=row.deviation if row else 0,
            version=record.version,
        )

    letter_views = sorted(
        (letter_view(each) for each in letters),
        key=lambda view: (
            _order(Attention(view.step) if view.step else None, view.deviation),
            -view.sent_on.toordinal(),
            str(view.id),
        ),
    )
    agreement_views = sorted(
        (agreement_view(each) for each in agreements),
        key=lambda view: (
            _order(Attention(view.step) if view.step else None, view.deviation),
            -view.moved_on.toordinal(),
            str(view.id),
        ),
    )
    return _Snapshot(
        today=today,
        thresholds=thresholds,
        letters=letter_views,
        letter_lines=[
            rules.LetterLine(
                id=view.id,
                organization_id=view.organization.id,
                state=LetterState(view.state),
                step=Attention(view.step) if view.step else None,
                due_on=view.due_on,
                days=view.days,
            )
            for view in letter_views
        ],
        agreements=agreement_views,
        agreement_lines=[
            rules.AgreementLine(id=view.id, sleeping=view.sleeping, quiet_days=view.quiet_days)
            for view in agreement_views
        ],
        organizations=organizations,
    )


def _organization_view(
    record: OrganizationRecord,
    snapshot: _Snapshot,
    *,
    ijro_lead: int,
    project_count: int,
) -> OrganizationView:
    own = [each for each in snapshot.letters if each.organization.id == record.id]
    replies = [
        each.days
        for each in own
        if each.direction == Direction.OUTGOING.value and each.state == LetterState.ANSWERED.value
    ]
    agreements = [each for each in snapshot.agreements if each.organization.id == record.id]
    ratings = {rating.value: 0 for rating in Rating}
    for each in own:
        if each.rating:
            ratings[each.rating] += 1
    return OrganizationView(
        id=record.id,
        name=record.name,
        short_name=record.short_name,
        kind=record.kind,
        is_founded_by_agency=record.is_founded_by_agency,
        phone=record.phone,
        email=record.email,
        waiting=sum(1 for each in own if each.state == LetterState.WAITING_REPLY.value),
        to_answer=sum(1 for each in own if each.state == LetterState.TO_ANSWER.value),
        agreement_count=len(agreements),
        sleeping=sum(1 for each in agreements if each.sleeping),
        overdue_steps=sum(1 for each in agreements if each.step == Attention.OVERDUE.value),
        ijro_lead=ijro_lead,
        project_count=project_count,
        speed={
            "letters": len(replies),
            "median_days": rules.speed(
                replies, min_letters=snapshot.thresholds.min_letters_for_speed
            ),
        },
        ratings=ratings,
    )


def _answer_view(answer: rules.Answer, snapshot: _Snapshot) -> dict[str, Any]:
    def org(org_id: uuid.UUID) -> OrganizationRef:
        return _ref(snapshot.organizations[org_id])

    base: dict[str, Any] = {"key": answer.key.value, "rows": list(answer.rows)}
    match answer.key:
        case Question.NOT_ANSWERING:
            return base | {
                "count": answer.count,
                "organizations": [
                    {
                        "organization": org(group.organization_id),
                        "count": group.count,
                        "oldest_days": group.oldest_days,
                        "rows": list(group.rows),
                    }
                    for group in answer.groups
                ],
            }
        case Question.TO_ANSWER:
            return base | {
                "count": answer.count,
                "overdue": answer.overdue,
                "nearest": (
                    {
                        "id": answer.nearest[0],
                        "due_on": answer.nearest[1],
                        "days": answer.nearest[2],
                    }
                    if answer.nearest
                    else None
                ),
            }
        case Question.SPEED:
            return base | {
                "measured": [
                    {
                        "organization": org(each.organization_id),
                        "median_days": each.median_days,
                        "letters": each.letters,
                    }
                    for each in answer.measured
                ],
                "little_data": answer.little_data,
                "min_letters": answer.min_letters,
            }
        case Question.SLEEPING:
            return base | {
                "count": answer.count,
                "oldest": (
                    {"id": answer.oldest[0], "days": answer.oldest[1]} if answer.oldest else None
                ),
            }
    raise AssertionError(f"вопрос без формы ответа: {answer.key}")


async def load(
    session: AsyncSession, *, now: datetime, zone: ZoneInfo, is_demo: bool
) -> InteractionView:
    """Раздел целиком: вопросы, письма и соглашения в порядке лестницы, организации."""
    today = local_date(now, zone)
    snapshot = await _snapshot(session, today=today, zone=zone)
    ijro_lead = await read_model.ijro_lead(session)
    projects = await read_model.projects(session)
    organizations = [
        _organization_view(
            record,
            snapshot,
            ijro_lead=len(ijro_lead.get(record.id, [])),
            project_count=len(projects.get(record.id, [])),
        )
        for record in snapshot.organizations.values()
    ]
    # Кого ждём и кому должны — первыми; остальные по имени.
    organizations.sort(
        key=lambda each: (-(each.waiting + each.to_answer), each.short_name or each.name)
    )
    speeds = [
        rules.OrganizationSpeed(
            organization_id=each.id,
            letters=int(each.speed["letters"] or 0),
            median_days=each.speed["median_days"],
        )
        for each in organizations
    ]
    found = metrics.interaction_answers(
        snapshot.letter_lines,
        speeds,
        snapshot.agreement_lines,
        today=today,
        thresholds=snapshot.thresholds,
    )
    people = await ijro_model.people(session)
    return InteractionView(
        as_of=now,
        thresholds={
            "burn_days": snapshot.thresholds.burn_days,
            "quiet_days": snapshot.thresholds.quiet_days,
            "sleeping_days": snapshot.thresholds.sleeping_days,
            "min_letters": snapshot.thresholds.min_letters_for_speed,
        },
        questions=[_answer_view(answer, snapshot) for answer in found],
        letters=snapshot.letters,
        organizations=organizations,
        agreements=snapshot.agreements,
        people=[PersonRef(id=person_id, name=name) for person_id, name in people],
        choices=[
            OrganizationRef(id=org_id, name=name, short_name=short)
            for org_id, name, short in await read_model.choices(session)
        ],
        is_demo=is_demo,
    )


async def organization(
    session: AsyncSession, *, organization_id: uuid.UUID, now: datetime, zone: ZoneInfo
) -> OrganizationCard:
    """Карточка организации — письма, соглашения, поручения, проекты (ТЗ 11)."""
    today = local_date(now, zone)
    record = await read_model.organization(session, organization_id)
    if record is None:
        raise NotFoundError("Организация не найдена: её могли удалить из справочника")
    snapshot = await _snapshot(session, today=today, zone=zone, organization_id=organization_id)
    snapshot.organizations[record.id] = record
    lead = (await read_model.ijro_lead(session)).get(organization_id, [])
    projects = (await read_model.projects(session)).get(organization_id, [])

    # Вклад SETA — тот же, что у Пульта и «Ижро»: без него ступень поручения в карточке
    # разошлась бы с лестницей, как только SETA подключат.
    assignments = (
        await ijro_model.records(
            session, zone=zone, ids=lead, seta=await metrics.seta_life(zone=zone)
        )
        if lead
        else []
    )
    documents = {each.id: each.code for each in await ijro_model.documents(session)}
    steps = metrics.steps(
        [ijro_model.item_of(each, None) for each in assignments],
        today=today,
        thresholds=snapshot.thresholds,
    )
    ijro = [
        {
            "id": each.id,
            "place": (
                f"{documents.get(each.document_id, '')} · {each.band}"
                if each.band
                else documents.get(each.document_id, "")
            ),
            "content": each.content,
            "step": steps[each.id].attention.value if each.id in steps else None,
        }
        for each in sorted(assignments, key=lambda each: (each.due_on or date.max, str(each.id)))
    ]
    return OrganizationCard(
        organization=_organization_view(
            record, snapshot, ijro_lead=len(lead), project_count=len(projects)
        ),
        letters=snapshot.letters,
        agreements=snapshot.agreements,
        ijro=ijro,
        projects=[
            {"id": each.id, "code": each.code, "title": each.title, "role": each.role}
            for each in projects
        ],
    )


# ---------------------------------------------------------------------------
# Правки
# ---------------------------------------------------------------------------


async def add_letter(session: AsyncSession, *, data: NewLetter, today: date) -> uuid.UUID:
    """Новое письмо — помощник. Обязательны направление, организация и тема (ТЗ 7)."""
    subject = rules.clean_subject(data.subject)
    number = rules.clean_number(data.number)
    if await read_model.organization(session, data.organization_id) is None:
        raise RuleViolationError("Организация не найдена в справочнике")
    if data.author_id is not None:
        author = await session.get(Person, data.author_id)
        if author is None or not author.is_active:
            raise RuleViolationError("Автор не найден в справочнике сотрудников")
    validate_horizon(data.sent_on, *([data.due_on] if data.due_on else []))
    if data.sent_on > today:
        raise RuleViolationError("Дата письма ещё не наступила")
    if data.due_on is not None and data.due_on < data.sent_on:
        raise RuleViolationError("Срок ответа не может быть раньше письма")
    letter = Letter(
        direction=data.direction.value,
        organization_id=data.organization_id,
        subject=subject,
        number=number,
        sent_on=data.sent_on,
        due_on=data.due_on,
        author_person_id=data.author_id,
    )
    session.add(letter)
    await session.flush()
    return letter.id


async def _letter(session: AsyncSession, letter_id: uuid.UUID) -> Letter:
    found = await read_model.letter(session, letter_id)
    if found is None:
        raise NotFoundError("Письмо не найдено: его могли удалить")
    return found


async def answer(
    session: AsyncSession,
    *,
    letter_id: uuid.UUID,
    on: date,
    number: str | None,
    version: int,
    today: date,
) -> None:
    """«Ответ получен» у исходящего, «Мы ответили» у входящего — помощник."""
    letter = await _letter(session, letter_id)
    check_version(expected=version, actual=letter.version)
    rules.check_answer(sent_on=letter.sent_on, answered_on=on, today=today)
    letter.answered_on = on
    letter.reply_number = rules.clean_number(number)


async def rate(
    session: AsyncSession, *, letter_id: uuid.UUID, rating: Rating | None, version: int
) -> None:
    """Оценка полученного ответа — руководитель, одно касание; `None` снимает её (V38)."""
    letter = await _letter(session, letter_id)
    check_version(expected=version, actual=letter.version)
    if rating is not None:
        rules.check_rating(Direction(letter.direction), letter.answered_on)
    letter.rating = rating.value if rating else None


async def next_step(
    session: AsyncSession,
    *,
    agreement_id: uuid.UUID,
    text: str | None,
    on: date | None,
    version: int,
    now: datetime,
) -> None:
    """Следующий шаг соглашения — и это его движение (V40): «спит» отсчитывается заново."""
    agreement = await read_model.agreement(session, agreement_id)
    if agreement is None:
        raise NotFoundError("Соглашение не найдено: его могли удалить")
    check_version(expected=version, actual=agreement.version)
    if on is not None:
        validate_horizon(on)
    agreement.next_step = rules.clean_next_step(text)
    agreement.next_step_on = on
    agreement.moved_at = now
