"""Подготовка: доклады и мероприятия (ТЗ 3.5, 5).

«Готовы ли мы к дате и кто задерживает?» — ответ складывается из этапа, дней до показа и
запросов сведений: каких сведений не хватает и от кого их ждём. Ступень подготовки считает
`app.domain.attention` тем же путём, что строку Пульта: показ — это срок, движение
подготовки — признак жизни.

Допущения (docs/OPEN-QUESTIONS.md): V41 — показ прошёл, а этап не «показ» — просрочено,
движение — правка этапа, пункта чек-листа или запроса; V42 — запрос просрочен, если срок
прошёл, а сведения не получены, задерживает тот, от кого их ждут; V43 — напоминание —
готовый текст, отправляет человек своим каналом.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.domain.errors import RuleViolationError

TITLE_MAX_LENGTH = 500
TEXT_MAX_LENGTH = 1000


class PreparationKind(StrEnum):
    REPORT = "report"
    EVENT = "event"


class PrepStage(StrEnum):
    """Этап подготовки (ТЗ 3.5). Последний — показ: после него подготовка закрыта."""

    THESES = "theses"
    DATA = "data"
    DRAFT = "draft"
    APPROVAL = "approval"
    REHEARSAL = "rehearsal"
    SHOWN = "shown"


class Addressee(StrEnum):
    CABINET = "cabinet"
    ADMINISTRATION = "administration"
    PRESIDENT = "president"
    PRIME_MINISTER = "prime_minister"
    OTHER = "other"


class VersionState(StrEnum):
    """Статус версии презентации (ТЗ 3.5): на просмотре, на доработке, принята."""

    REVIEW = "review"
    REWORK = "rework"
    ACCEPTED = "accepted"


COMMENT_MAX_LENGTH = 2000


class RequestState(StrEnum):
    """Состояние запроса сведений — считается, не хранится (инвариант 1)."""

    REQUESTED = "requested"
    RECEIVED = "received"
    OVERDUE = "overdue"


class SourceKind(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"


class Question(StrEnum):
    READINESS = "readiness"
    START_NOW = "start_now"


def request_state(
    *, due_on: date | None, received_on: date | None, today: date
) -> tuple[RequestState, int]:
    """Состояние запроса и сколько дней задерживают (V42)."""
    if received_on is not None:
        return RequestState.RECEIVED, 0
    if due_on is not None and due_on < today:
        return RequestState.OVERDUE, (today - due_on).days
    return RequestState.REQUESTED, 0


def clean_title(title: str) -> str:
    value = " ".join(title.split())
    if not value:
        raise RuleViolationError("Напишите название")
    if len(value) > TITLE_MAX_LENGTH:
        raise RuleViolationError(f"Название длиннее {TITLE_MAX_LENGTH} знаков")
    return value


def clean_text(text: str, *, what: str) -> str:
    value = " ".join(text.split())
    if not value:
        raise RuleViolationError(f"Напишите {what}")
    if len(value) > TEXT_MAX_LENGTH:
        raise RuleViolationError(f"Текст длиннее {TEXT_MAX_LENGTH} знаков")
    return value


def check_dates(*, show_on: date, start_on: date | None) -> None:
    if start_on is not None and start_on > show_on:
        raise RuleViolationError("Начать готовить нужно до даты показа")


@dataclass(frozen=True, slots=True)
class RequestLine:
    id: uuid.UUID
    source_kind: SourceKind
    source_id: uuid.UUID
    state: RequestState
    late_days: int


@dataclass(frozen=True, slots=True)
class Delay:
    """«Кто задерживает»: источник, сколько просроченных сведений и дольше всего на сколько."""

    source_kind: SourceKind
    source_id: uuid.UUID
    days: int
    requests: tuple[uuid.UUID, ...]

    @property
    def count(self) -> int:
        return len(self.requests)


def delays(requests: Iterable[RequestLine]) -> list[Delay]:
    """Просроченные запросы по источникам — дольше всех задерживающий первым."""
    grouped: dict[tuple[SourceKind, uuid.UUID], list[RequestLine]] = {}
    for each in requests:
        if each.state is RequestState.OVERDUE:
            grouped.setdefault((each.source_kind, each.source_id), []).append(each)
    found = [
        Delay(
            source_kind=kind,
            source_id=source,
            days=max(each.late_days for each in own),
            requests=tuple(each.id for each in own),
        )
        for (kind, source), own in grouped.items()
    ]
    return sorted(found, key=lambda each: (-each.days, -each.count, str(each.source_id)))


@dataclass(frozen=True, slots=True)
class PrepLine:
    id: uuid.UUID
    stage: PrepStage
    show_on: date
    start_on: date | None
    missing: int
    """Сведений не получено (запрошено и просрочено)."""

    delays: tuple[Delay, ...]


@dataclass(frozen=True, slots=True)
class Answer:
    key: Question
    rows: tuple[uuid.UUID, ...]
    count: int = 0
    nearest: PrepLine | None = None


def answers(lines: Sequence[PrepLine], *, today: date) -> list[Answer]:
    """Два ответа раздела; `lines` — в порядке лестницы."""
    open_lines = [each for each in lines if each.stage is not PrepStage.SHOWN]
    missing = [each for each in open_lines if each.missing > 0]
    upcoming = sorted(
        (each for each in open_lines if each.show_on >= today),
        key=lambda each: (each.show_on, str(each.id)),
    )
    start_now = [
        each
        for each in open_lines
        if each.stage is PrepStage.THESES and each.start_on is not None and each.start_on <= today
    ]
    # Ближайшая подготовка, где сведений не хватает: о ней и спрашивает руководитель
    # («не хватает N сведений; X задерживает M дн», ТЗ 5). Всё собрано — ближайшая вообще.
    lacking = [each for each in upcoming if each.missing > 0]
    nearest = lacking[0] if lacking else (upcoming[0] if upcoming else None)
    return [
        Answer(
            key=Question.READINESS,
            rows=tuple(each.id for each in missing),
            count=len(missing),
            nearest=nearest,
        ),
        Answer(
            key=Question.START_NOW,
            rows=tuple(each.id for each in start_now),
            count=len(start_now),
        ),
    ]
