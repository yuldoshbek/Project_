"""Доклады и мероприятия — подготовка, чек-лист, запросы сведений (ТЗ 3.5, 5).

Форма — договор экрана `frontend/src/sections/reports/model.ts`.

**Числа — из `app.services.metrics`** (инвариант 2): ступень подготовки считает тот же
`build_ladder`, что строит Пульт; «кто задерживает» и ответы — `app.domain.preparations`.

**Роль подписывает действие** (инвариант 13): подготовку, этап, пункты и запросы ведёт
помощник; руководитель смотрит и решает кнопками строки Пульта.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import preparations as rules
from app.domain.attention import Attention, sort_key
from app.domain.clock import local_date
from app.domain.decisions import DecisionTarget
from app.domain.errors import NotFoundError, RuleViolationError, check_version
from app.domain.preparations import Addressee, PreparationKind, PrepStage, SourceKind
from app.domain.projects import validate_horizon
from app.repos import ijro as people_model
from app.repos import preparations as read_model
from app.repos import pult as pult_model
from app.repos.models import (
    InfoRequest,
    Organization,
    Person,
    Preparation,
    PreparationItem,
    Project,
)
from app.repos.preparations import PrepRecord, RequestRecord
from app.services import files, metrics


@dataclass(frozen=True, slots=True)
class NewPreparation:
    kind: PreparationKind
    title: str
    show_on: date
    start_on: date | None
    addressee: Addressee | None
    responsible_id: uuid.UUID | None
    project_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class NewRequest:
    what: str
    source_kind: SourceKind
    source_id: uuid.UUID
    due_on: date | None


def _source(record: RequestRecord) -> dict[str, Any]:
    return {"kind": record.source_kind.value, "id": record.source_id, "name": record.source_name}


async def _rows(
    session: AsyncSession, *, today: date, zone: ZoneInfo, ids: list[uuid.UUID] | None = None
) -> tuple[list[dict[str, Any]], list[rules.PrepLine], dict[uuid.UUID, list[RequestRecord]]]:
    """Строки раздела в порядке лестницы, строки для ответов и запросы по подготовке."""
    thresholds = await metrics.load_thresholds(session)
    records = await read_model.records(session, zone=zone, ids=ids)
    prep_ids = [each.id for each in records]
    requests: dict[uuid.UUID, list[RequestRecord]] = {}
    for request in await read_model.info_requests(session, prep_ids):
        requests.setdefault(request.preparation_id, []).append(request)
    items: dict[uuid.UUID, list[read_model.ItemRecord]] = {}
    for item in await read_model.checklist(session, prep_ids):
        items.setdefault(item.preparation_id, []).append(item)

    targets = [(DecisionTarget.PREPARATION.value, each.id) for each in records]
    questions = await pult_model.open_questions(session, targets)

    def asked(record: PrepRecord) -> date | None:
        question = questions.get((DecisionTarget.PREPARATION.value, record.id))
        return local_date(question.created_at, zone) if question else None

    ladder = metrics.steps(
        [
            item
            for item in (read_model.item_of(each, asked(each)) for each in records)
            if item is not None
        ],
        today=today,
        thresholds=thresholds,
    )

    rows: list[dict[str, Any]] = []
    lines: list[rules.PrepLine] = []
    for record in records:
        own = requests.get(record.id, [])
        states = [
            rules.request_state(due_on=each.due_on, received_on=each.received_on, today=today)
            for each in own
        ]
        request_lines = [
            rules.RequestLine(each.id, each.source_kind, each.source_id, state, late)
            for each, (state, late) in zip(own, states, strict=True)
        ]
        delays = rules.delays(request_lines)
        names = {(each.source_kind, each.source_id): _source(each) for each in own}
        delay_views = [
            {
                "source": names[(delay.source_kind, delay.source_id)],
                "count": delay.count,
                "days": delay.days,
                "requests": list(delay.requests),
            }
            for delay in delays
        ]
        checklist = items.get(record.id, [])
        row = ladder.get(record.id)
        missing = sum(1 for state, _ in states if state is not rules.RequestState.RECEIVED)
        rows.append(
            {
                "id": record.id,
                "kind": record.kind,
                "title": record.title,
                "addressee": record.addressee,
                "show_on": record.show_on,
                "start_on": record.start_on,
                "responsible": (
                    {"id": record.responsible_id, "name": record.responsible_name}
                    if record.responsible_id and record.responsible_name
                    else None
                ),
                "stage": record.stage.value,
                "link": (
                    {"type": "project", "id": record.project[0], "title": record.project[1]}
                    if record.project
                    else None
                ),
                "checklist": {
                    "done": sum(1 for each in checklist if each.is_done),
                    "total": len(checklist),
                },
                "requests": {
                    "total": len(own),
                    "received": sum(
                        1 for state, _ in states if state is rules.RequestState.RECEIVED
                    ),
                    "overdue": sum(1 for state, _ in states if state is rules.RequestState.OVERDUE),
                },
                "delays": delay_views,
                "days_left": (record.show_on - today).days,
                "step": row.attention.value if row else None,
                "deviation": row.deviation if row else 0,
                "version": record.version,
                "_items": checklist,
                "_requests": list(zip(own, states, strict=True)),
            }
        )
        lines.append(
            rules.PrepLine(
                id=record.id,
                stage=record.stage,
                show_on=record.show_on,
                start_on=record.start_on,
                missing=missing,
                delays=tuple(delays),
            )
        )

    def order(row: dict[str, Any]) -> tuple[Any, ...]:
        step = Attention(row["step"]) if row["step"] else Attention.ON_TRACK
        shown = row["stage"] == PrepStage.SHOWN.value
        rank, urgency, _ = sort_key(step, row["deviation"], None)
        # Прошедшие показы — в конце: готовиться к ним уже нечего.
        return (shown, rank, urgency, row["show_on"], str(row["id"]))

    rows.sort(key=order)
    by_id = {line.id: line for line in lines}
    return rows, [by_id[row["id"]] for row in rows], requests


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


async def load(
    session: AsyncSession, *, now: datetime, zone: ZoneInfo, is_demo: bool
) -> dict[str, Any]:
    today = local_date(now, zone)
    rows, lines, _ = await _rows(session, today=today, zone=zone)
    by_id = {row["id"]: row for row in rows}
    found = rules.answers(lines, today=today)
    questions: list[dict[str, Any]] = []
    for answer in found:
        if answer.key is rules.Question.READINESS:
            nearest = answer.nearest
            row = by_id.get(nearest.id) if nearest else None
            questions.append(
                {
                    "key": answer.key.value,
                    "count": answer.count,
                    "rows": list(answer.rows),
                    "nearest": (
                        {
                            "id": row["id"],
                            "title": row["title"],
                            "days_left": row["days_left"],
                            "missing": nearest.missing if nearest else 0,
                            "delay": row["delays"][0] if row["delays"] else None,
                        }
                        if row
                        else None
                    ),
                }
            )
        else:
            questions.append(
                {"key": answer.key.value, "count": answer.count, "rows": list(answer.rows)}
            )
    people = await people_model.people(session)
    return {
        "as_of": now,
        "questions": questions,
        "items": [_public(row) for row in rows],
        "people": [{"id": person_id, "name": name} for person_id, name in people],
        "organizations": [
            {"id": org_id, "name": name, "short_name": short}
            for org_id, name, short in await read_model.organizations(session)
        ],
        "projects": [
            {"id": project_id, "code": code, "title": title}
            for project_id, code, title in await read_model.projects(session)
        ],
        "is_demo": is_demo,
    }


async def card(
    session: AsyncSession, *, preparation_id: uuid.UUID, now: datetime, zone: ZoneInfo
) -> dict[str, Any]:
    today = local_date(now, zone)
    rows, _, _ = await _rows(session, today=today, zone=zone, ids=[preparation_id])
    if not rows:
        raise NotFoundError("Подготовка не найдена: её могли удалить")
    row = rows[0]
    return _public(row) | {
        "versions": await files.versions(session, preparation_id=preparation_id, zone=zone),
        "items": [
            {"id": each.id, "text": each.text, "is_done": each.is_done, "version": each.version}
            for each in row["_items"]
        ],
        "info_requests": [
            {
                "id": each.id,
                "what": each.what,
                "source": _source(each),
                "due_on": each.due_on,
                "received_on": each.received_on,
                "state": state.value,
                "late_days": late,
                "version": each.version,
            }
            for each, (state, late) in row["_requests"]
        ],
    }


# ---------------------------------------------------------------------------
# Правки
# ---------------------------------------------------------------------------


async def _preparation(session: AsyncSession, preparation_id: uuid.UUID) -> Preparation:
    found = await session.get(Preparation, preparation_id)
    if found is None:
        raise NotFoundError("Подготовка не найдена: её могли удалить")
    return found


async def _check_person(session: AsyncSession, person_id: uuid.UUID | None) -> None:
    if person_id is None:
        return
    person = await session.get(Person, person_id)
    if person is None or not person.is_active:
        raise RuleViolationError("Сотрудник не найден в справочнике")


async def create(session: AsyncSession, *, data: NewPreparation) -> uuid.UUID:
    """Новая подготовка: вид, название и дата показа (ТЗ 7 — минимум полей)."""
    title = rules.clean_title(data.title)
    validate_horizon(data.show_on, *([data.start_on] if data.start_on else []))
    rules.check_dates(show_on=data.show_on, start_on=data.start_on)
    if data.addressee is not None and data.kind is not PreparationKind.REPORT:
        raise RuleViolationError("Адресат бывает только у доклада")
    await _check_person(session, data.responsible_id)
    if data.project_id is not None and await session.get(Project, data.project_id) is None:
        raise RuleViolationError("Проект не найден")
    preparation = Preparation(
        kind=data.kind.value,
        title=title,
        show_on=data.show_on,
        start_on=data.start_on,
        addressee=data.addressee.value if data.addressee else None,
        responsible_person_id=data.responsible_id,
        project_id=data.project_id,
        stage=PrepStage.THESES.value,
    )
    session.add(preparation)
    await session.flush()
    return preparation.id


async def set_stage(
    session: AsyncSession, *, preparation_id: uuid.UUID, stage: PrepStage, version: int
) -> None:
    preparation = await _preparation(session, preparation_id)
    check_version(expected=version, actual=preparation.version)
    if preparation.stage != stage.value:
        preparation.stage = stage.value


async def add_item(session: AsyncSession, *, preparation_id: uuid.UUID, text: str) -> uuid.UUID:
    await _preparation(session, preparation_id)
    last = await session.scalar(
        select(func.max(PreparationItem.sort_order)).where(
            PreparationItem.preparation_id == preparation_id
        )
    )
    item = PreparationItem(
        preparation_id=preparation_id,
        text=rules.clean_text(text, what="пункт"),
        sort_order=(last or 0) + 1,
    )
    session.add(item)
    await session.flush()
    return item.id


async def toggle_item(
    session: AsyncSession,
    *,
    preparation_id: uuid.UUID,
    item_id: uuid.UUID,
    done: bool,
    version: int,
) -> None:
    item = await session.get(PreparationItem, item_id)
    if item is None or item.preparation_id != preparation_id:
        raise NotFoundError("Пункт не найден: его могли удалить")
    check_version(expected=version, actual=item.version)
    item.is_done = done


async def add_request(
    session: AsyncSession, *, preparation_id: uuid.UUID, data: NewRequest
) -> uuid.UUID:
    """Запрос сведений — от сотрудника или организации, со сроком (ТЗ 3.5)."""
    await _preparation(session, preparation_id)
    if data.source_kind is SourceKind.PERSON:
        await _check_person(session, data.source_id)
    elif await session.get(Organization, data.source_id) is None:
        raise RuleViolationError("Организация не найдена в справочнике")
    if data.due_on is not None:
        validate_horizon(data.due_on)
    request = InfoRequest(
        preparation_id=preparation_id,
        what=rules.clean_text(data.what, what="что нужно"),
        source_person_id=data.source_id if data.source_kind is SourceKind.PERSON else None,
        source_organization_id=(
            data.source_id if data.source_kind is SourceKind.ORGANIZATION else None
        ),
        due_on=data.due_on,
    )
    session.add(request)
    await session.flush()
    return request.id


async def receive(
    session: AsyncSession,
    *,
    preparation_id: uuid.UUID,
    request_id: uuid.UUID,
    received_on: date | None,
    version: int,
    today: date,
) -> None:
    """Сведения получены — или отметка снята, если поставили по ошибке."""
    request = await session.get(InfoRequest, request_id)
    if request is None or request.preparation_id != preparation_id:
        raise NotFoundError("Запрос не найден: его могли удалить")
    check_version(expected=version, actual=request.version)
    if received_on is not None and received_on > today:
        raise RuleViolationError("Дата получения ещё не наступила")
    request.received_on = received_on
