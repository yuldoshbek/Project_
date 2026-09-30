"""Управление — обход, пороги, справочники, доступ.

Форма ответа — договор экрана `frontend/src/sections/management/model.ts`: экран утверждён
заказчиком 29.09.2026 на вымышленных данных той же формы, и API написан под него
(CLAUDE.md, цикл блока). Устройства и перевыпуск ссылок — прежние пути `/api/access/…`.

Смотрят оба — одной формой ответа (инвариант 13); правит помощник (`Assistant`, ТЗ 1.2:
«Управление — только помощник»). Предпросмотр порога ничего не пишет и открыт обоим.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SessionDep, SettingsDep, is_demo
from app.api.security import Assistant, CurrentUser
from app.api.transaction import transactional_router
from app.domain.clock import now_utc
from app.domain.dictionaries import OrganizationKind
from app.domain.errors import RuleViolationError
from app.domain.management import RecordKind, RoundAction, RoundReason
from app.services import management as service

router = transactional_router(tags=["управление"])


class Strict(BaseModel):
    # Неизвестное поле — отказ: опечатка в имени не должна тихо стать пустым значением.
    model_config = ConfigDict(extra="forbid")


class Target(BaseModel):
    kind: Literal["project", "task"]
    id: uuid.UUID


class Record(BaseModel):
    kind: RecordKind
    id: uuid.UUID
    version: int


class RoundItem(BaseModel):
    id: str
    reason: RoundReason
    target: Target
    record: Record
    title: str
    owner: str | None
    responsible: str | None
    days: int
    actions: list[RoundAction]


class Round(BaseModel):
    week_from: date
    week_to: date
    items: list[RoundItem]
    done: int


class Threshold(BaseModel):
    key: str
    value: int | str
    default: int | str
    origin: Literal["tz", "assumption"]
    kind: Literal["days", "count", "time"]
    # У времени границы — строки «ЧЧ:ММ» (окно сводки), у дней и счёта — числа.
    min: int | str | None
    max: int | str | None
    affected: int | None
    version: int


class Entry(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    used: int
    version: int
    org_kind: str | None = None
    is_center: bool | None = None


class Group(BaseModel):
    kind: str
    entries: list[Entry]
    can_add: bool
    can_disable: bool
    can_move: bool


class Step(BaseModel):
    id: uuid.UUID
    name: str
    offset_days: int
    version: int


class Person(BaseModel):
    id: uuid.UUID
    name: str


class Link(BaseModel):
    role: str
    issued_at: datetime | None
    last_login_at: datetime | None


class ManagementResponse(BaseModel):
    as_of: datetime
    round: Round
    thresholds: list[Threshold]
    dictionaries: list[Group]
    templates: dict[str, list[Step]]
    people: list[Person]
    links: list[Link]
    is_demo: bool


def _item(view: service.RoundItemView) -> RoundItem:
    return RoundItem(
        id=f"{view.reason.value}:{view.record_id}",
        reason=view.reason,
        target=Target(kind=view.target_kind, id=view.target_id),
        record=Record(kind=view.record_kind, id=view.record_id, version=view.version),
        title=view.title,
        owner=view.owner,
        responsible=view.responsible,
        days=view.days,
        actions=view.actions,
    )


@router.get("/management", response_model=ManagementResponse, summary="Управление: весь раздел")
async def read_management(
    user: CurrentUser, session: SessionDep, settings: SettingsDep
) -> ManagementResponse:
    view = await service.load(
        session, now=now_utc(), zone=ZoneInfo(settings.timezone), is_demo=is_demo(settings)
    )
    return ManagementResponse(
        as_of=view.as_of,
        round=Round(
            week_from=view.round.week_from,
            week_to=view.round.week_to,
            items=[_item(item) for item in view.round.items],
            done=view.round.done,
        ),
        thresholds=[
            Threshold(
                key=each.key.value,
                value=each.value,
                default=each.default,
                origin=each.origin,
                kind=each.kind,
                min=each.low,
                max=each.high,
                affected=each.affected,
                version=each.version,
            )
            for each in view.thresholds
        ],
        dictionaries=[
            Group(
                kind=group.kind.value,
                entries=[
                    Entry(
                        id=entry.id,
                        name=entry.name,
                        is_active=entry.is_active,
                        used=entry.used,
                        version=entry.version,
                        org_kind=entry.org_kind,
                        is_center=entry.is_center,
                    )
                    for entry in group.entries
                ],
                can_add=group.kind.can_add,
                can_disable=group.kind.can_disable,
                can_move=group.kind.can_move,
            )
            for group in view.dictionaries
        ],
        templates={
            str(type_id): [
                Step(id=step.id, name=step.name, offset_days=step.offset_days, version=step.version)
                for step in steps
            ]
            for type_id, steps in view.templates.items()
        },
        people=[Person(id=person_id, name=name) for person_id, name in view.people],
        links=[
            Link(role=link.role, issued_at=link.issued_at, last_login_at=link.last_login_at)
            for link in view.links
        ],
        is_demo=view.is_demo,
    )


class RoundActionRequest(Strict):
    reason: RoundReason
    record_kind: RecordKind
    record_id: uuid.UUID
    action: RoundAction
    version: int
    input: str | None = Field(default=None, max_length=500)


@router.post(
    "/management/round",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Действие обхода в одно касание",
)
async def round_action(
    body: RoundActionRequest, user: Assistant, session: SessionDep, settings: SettingsDep
) -> None:
    await service.act(
        session,
        step=service.RoundStep(
            reason=body.reason,
            record_kind=body.record_kind,
            record_id=body.record_id,
            action=body.action,
            version=body.version,
            input=body.input,
        ),
        now=now_utc(),
        zone=ZoneInfo(settings.timezone),
    )


class Preview(BaseModel):
    affected: int | None


def _value(raw: str) -> int | str:
    """Значение из строки запроса: число — числом, время — строкой «ЧЧ:ММ»."""
    try:
        return int(raw)
    except ValueError:
        return raw


@router.get(
    "/management/thresholds/{key}/preview",
    response_model=Preview,
    summary="Сколько строк сделает сигналом порог с этим значением — без записи",
)
async def preview_threshold(
    key: str,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    value: str = Query(max_length=10, description="Значение порога, которое примеряют"),
) -> Preview:
    return Preview(
        affected=await service.preview(
            session, key=key, value=_value(value), now=now_utc(), zone=ZoneInfo(settings.timezone)
        )
    )


class ThresholdRequest(Strict):
    value: int | str
    version: int


@router.put(
    "/management/thresholds/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Новое значение порога",
)
async def update_threshold(
    key: str, body: ThresholdRequest, user: Assistant, session: SessionDep
) -> None:
    await service.save_threshold(session, key=key, value=body.value, version=body.version)


class RenameRequest(Strict):
    name: str = Field(min_length=1, max_length=300)
    version: int
    org_kind: OrganizationKind | None = None


@router.put(
    "/management/dictionaries/{kind}/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Переименовать значение справочника; у организации — и вид",
)
async def rename_entry(
    kind: str, entry_id: uuid.UUID, body: RenameRequest, user: Assistant, session: SessionDep
) -> None:
    await service.rename(
        session,
        kind=kind,
        entry_id=entry_id,
        name=body.name,
        version=body.version,
        org_kind=body.org_kind,
    )


class VersionRequest(Strict):
    version: int


@router.post(
    "/management/dictionaries/{kind}/{entry_id}/toggle",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Выключить или включить значение справочника",
)
async def toggle_entry(
    kind: str, entry_id: uuid.UUID, body: VersionRequest, user: Assistant, session: SessionDep
) -> None:
    await service.toggle(session, kind=kind, entry_id=entry_id, version=body.version)


class MoveRequest(Strict):
    step: Literal[-1, 1]
    version: int


@router.post(
    "/management/dictionaries/{kind}/{entry_id}/move",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Выше или ниже в формах",
)
async def move_entry(
    kind: str, entry_id: uuid.UUID, body: MoveRequest, user: Assistant, session: SessionDep
) -> None:
    await service.move(session, kind=kind, entry_id=entry_id, step=body.step, version=body.version)


class NewEntryRequest(Strict):
    name: str = Field(min_length=1, max_length=300)
    org_kind: OrganizationKind | None = None


class Created(BaseModel):
    id: uuid.UUID


@router.post(
    "/management/dictionaries/{kind}",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Новое значение справочника",
)
async def create_entry(
    kind: str, body: NewEntryRequest, user: Assistant, session: SessionDep
) -> Created:
    return Created(id=await service.add(session, kind=kind, name=body.name, org_kind=body.org_kind))


class StepRequest(Strict):
    name: str = Field(min_length=1, max_length=200)
    offset_days: int


class StepEditRequest(StepRequest):
    version: int


@router.post(
    "/management/templates/{type_id}/steps",
    response_model=Created,
    status_code=status.HTTP_201_CREATED,
    summary="Новая веха шаблона типа проекта",
)
async def create_step(
    type_id: uuid.UUID, body: StepRequest, user: Assistant, session: SessionDep
) -> Created:
    return Created(
        id=await service.add_step(
            session, type_id=type_id, name=body.name, offset_days=body.offset_days
        )
    )


@router.put(
    "/management/templates/{type_id}/steps/{step_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Веха шаблона: название и через сколько дней от начала",
)
async def update_step(
    type_id: uuid.UUID,
    step_id: uuid.UUID,
    body: StepEditRequest,
    user: Assistant,
    session: SessionDep,
) -> None:
    await service.edit_step(
        session,
        type_id=type_id,
        step_id=step_id,
        name=body.name,
        offset_days=body.offset_days,
        version=body.version,
    )


@router.delete(
    "/management/templates/{type_id}/steps/{step_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Убрать веху из шаблона",
)
async def delete_step(
    type_id: uuid.UUID,
    step_id: uuid.UUID,
    user: Assistant,
    session: SessionDep,
    version: int = Query(description="Версия вехи шаблона, которую видел человек"),
) -> None:
    if version < 1:
        raise RuleViolationError("Версия — целое число от 1")
    await service.remove_step(session, type_id=type_id, step_id=step_id, version=version)
