"""Взаимодействие: письма, соглашения и вопросы раздела (ТЗ 3.4, 4, 5).

Экран утверждён заказчиком 01.10.2026 на вымышленных данных
(`frontend/src/sections/interaction/demo.ts`): здесь те же правила на сервере, чтобы числа
считались в одном месте (инвариант 2). Ступени писем и соглашений приходят готовыми — их
считает `app.domain.attention` через `app.services.metrics`, тем же путём, что строки
Пульта.

Чистые функции: снимок → ответы. Базы и часов здесь нет; «сегодня» и пороги — аргументы.

Допущения (docs/OPEN-QUESTIONS.md): V38 — оценивается ответ на наше исходящее; V39 —
исходящее без срока «зависит от чужих» после порога молчания; V40 — движение соглашения —
правка следующего шага или его даты.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.domain.attention import Attention
from app.domain.errors import RuleViolationError

SUBJECT_MAX_LENGTH = 500
NUMBER_MAX_LENGTH = 100
NEXT_STEP_MAX_LENGTH = 1000

DEFAULT_SLEEPING_DAYS = 90
"""«Спит» — соглашение без движения дольше 90 дней (ТЗ 5); значение — в справочнике порогов."""


class Direction(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class Rating(StrEnum):
    """Оценка полученного ответа руководителем (ТЗ 3.4, 11; V38)."""

    SUBSTANCE = "substance"
    FORMAL = "formal"
    OFF_TOPIC = "off_topic"


class AgreementKind(StrEnum):
    MEMORANDUM = "memorandum"
    CONTRACT = "contract"


class LetterState(StrEnum):
    """Что с письмом — считается, не хранится (инвариант 1).

    Ждём ответа — наше исходящее без ответа; должны ответить — входящее, на которое мы не
    ответили; отвечено — ответ есть.
    """

    WAITING_REPLY = "waiting_reply"
    TO_ANSWER = "to_answer"
    ANSWERED = "answered"


class Question(StrEnum):
    """Четыре вопроса раздела (ТЗ 5). Порядок объявления — порядок на экране."""

    NOT_ANSWERING = "not_answering"
    TO_ANSWER = "to_answer"
    SPEED = "speed"
    SLEEPING = "sleeping"


def letter_state(direction: Direction, answered_on: date | None) -> LetterState:
    if answered_on is not None:
        return LetterState.ANSWERED
    return LetterState.WAITING_REPLY if direction is Direction.OUTGOING else LetterState.TO_ANSWER


def median_days(values: Sequence[int]) -> int:
    """Медиана с округлением половины вверх: 9,5 дня — «10 дн», как на экране.

    Медиана, а не среднее: одно письмо, на которое отвечали полгода, сделало бы «среднюю
    скорость» ведомства враньём — а руководитель решает по ней, писать ли второй раз.
    """
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle] + 1) // 2


def speed(answer_days: Sequence[int], *, min_letters: int) -> int | None:
    """Скорость ответа организации — только при `min_letters` ответах и больше (ТЗ 4)."""
    return median_days(answer_days) if len(answer_days) >= min_letters else None


# ---------------------------------------------------------------------------
# Проверка ввода
# ---------------------------------------------------------------------------


def clean_subject(subject: str) -> str:
    value = " ".join(subject.split())
    if not value:
        raise RuleViolationError("Напишите тему письма")
    if len(value) > SUBJECT_MAX_LENGTH:
        raise RuleViolationError(f"Тема письма длиннее {SUBJECT_MAX_LENGTH} знаков")
    return value


def clean_number(number: str | None) -> str | None:
    value = (number or "").strip()
    if len(value) > NUMBER_MAX_LENGTH:
        raise RuleViolationError(f"Номер письма длиннее {NUMBER_MAX_LENGTH} знаков")
    return value or None


def check_answer(*, sent_on: date, answered_on: date, today: date) -> None:
    """Ответ не раньше письма и не в будущем: такой датой скорость ответа соврала бы."""
    if answered_on < sent_on:
        raise RuleViolationError("Ответ не может быть раньше письма")
    if answered_on > today:
        raise RuleViolationError("Дата ответа ещё не наступила")


def check_rating(direction: Direction, answered_on: date | None) -> None:
    """Оценивается полученный ответ на наше письмо (V38)."""
    if direction is not Direction.OUTGOING or answered_on is None:
        raise RuleViolationError("Оценивается полученный ответ на наше письмо")


def clean_next_step(text: str | None) -> str | None:
    value = (text or "").strip()
    if len(value) > NEXT_STEP_MAX_LENGTH:
        raise RuleViolationError(f"Следующий шаг длиннее {NEXT_STEP_MAX_LENGTH} знаков")
    return value or None


# ---------------------------------------------------------------------------
# Ответы
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LetterLine:
    """Письмо со всем, из чего считаются ответы. Ступень — уже посчитанная."""

    id: uuid.UUID
    organization_id: uuid.UUID
    state: LetterState
    step: Attention | None
    due_on: date | None
    days: int
    """У неотвеченного — сколько дней ждёт, у отвеченного — за сколько ответили."""


@dataclass(frozen=True, slots=True)
class OrganizationSpeed:
    organization_id: uuid.UUID
    letters: int
    median_days: int | None


@dataclass(frozen=True, slots=True)
class AgreementLine:
    id: uuid.UUID
    sleeping: bool
    quiet_days: int


@dataclass(frozen=True, slots=True)
class WaitingGroup:
    organization_id: uuid.UUID
    oldest_days: int
    rows: tuple[uuid.UUID, ...]

    @property
    def count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True, slots=True)
class Answer:
    """Ответ: число или фраза и **те же строки**, что считались (ТЗ 5)."""

    key: Question
    rows: tuple[uuid.UUID, ...]
    count: int = 0
    overdue: int = 0
    groups: tuple[WaitingGroup, ...] = ()
    nearest: tuple[uuid.UUID, date, int] | None = None
    measured: tuple[OrganizationSpeed, ...] = ()
    little_data: int = 0
    min_letters: int = 0
    oldest: tuple[uuid.UUID, int] | None = None


def _ids(items: Iterable[LetterLine | AgreementLine]) -> tuple[uuid.UUID, ...]:
    return tuple(each.id for each in items)


def answers(
    letters: Sequence[LetterLine],
    speeds: Sequence[OrganizationSpeed],
    agreements: Sequence[AgreementLine],
    *,
    today: date,
    min_letters: int,
) -> list[Answer]:
    """Четыре ответа в порядке `Question`. Письма и соглашения — в порядке лестницы."""

    def not_answering() -> Answer:
        rows = [each for each in letters if each.state is LetterState.WAITING_REPLY]
        groups: dict[uuid.UUID, list[LetterLine]] = {}
        for each in rows:
            groups.setdefault(each.organization_id, []).append(each)
        return Answer(
            key=Question.NOT_ANSWERING,
            rows=_ids(rows),
            count=len(rows),
            groups=tuple(
                sorted(
                    (
                        WaitingGroup(org, max(each.days for each in own), _ids(own))
                        for org, own in groups.items()
                    ),
                    key=lambda group: (
                        -group.count,
                        -group.oldest_days,
                        str(group.organization_id),
                    ),
                )
            ),
        )

    def to_answer() -> Answer:
        rows = [each for each in letters if each.state is LetterState.TO_ANSWER]
        upcoming = sorted(
            (each for each in rows if each.due_on is not None and each.due_on >= today),
            key=lambda each: (each.due_on or today, str(each.id)),
        )
        first = upcoming[0] if upcoming else None
        return Answer(
            key=Question.TO_ANSWER,
            rows=_ids(rows),
            count=len(rows),
            overdue=sum(1 for each in rows if each.step is Attention.OVERDUE),
            nearest=(
                (first.id, first.due_on, (first.due_on - today).days)
                if first and first.due_on
                else None
            ),
        )

    def speed_answer() -> Answer:
        measured = sorted(
            (each for each in speeds if each.median_days is not None),
            key=lambda each: (-(each.median_days or 0), str(each.organization_id)),
        )
        return Answer(
            key=Question.SPEED,
            rows=tuple(each.organization_id for each in measured),
            measured=tuple(measured),
            little_data=sum(1 for each in speeds if each.letters > 0 and each.median_days is None),
            min_letters=min_letters,
        )

    def sleeping() -> Answer:
        rows = [each for each in agreements if each.sleeping]
        top = max(rows, key=lambda each: (each.quiet_days, str(each.id)), default=None)
        return Answer(
            key=Question.SLEEPING,
            rows=_ids(rows),
            count=len(rows),
            oldest=(top.id, top.quiet_days) if top else None,
        )

    rules = {
        Question.NOT_ANSWERING: not_answering,
        Question.TO_ANSWER: to_answer,
        Question.SPEED: speed_answer,
        Question.SLEEPING: sleeping,
    }
    return [rules[key]() for key in Question]
