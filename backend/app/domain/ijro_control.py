"""Ижро: правила над реестром — признак жизни, промежуточный срок, вопросы и стена.

Экран раздела утверждён заказчиком 30.09.2026 на вымышленных данных
(`frontend/src/sections/ijro/demo.ts`): здесь те же правила, перенесённые на сервер, чтобы
числа считались в одном месте (инвариант 2). Ступень лестницы сюда приходит готовой — её
считает `app.domain.attention` через `app.services.metrics`, тем же путём, что строку
Пульта.

Чистые функции: снимок строк → ответы. Базы и часов здесь нет; «сегодня» и пороги —
аргументы.

Допущения (docs/OPEN-QUESTIONS.md): V31 — двенадцать вопросов; V32 — этапы; V33 — точность
срока; V34 — «Разложить на задачу»; V3 — промежуточный срок; V36 — «близкий срок» вопроса
«работает ли ответственный?».
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from app.domain.attention import Attention
from app.domain.errors import RuleViolationError
from app.domain.ijro import (
    OPEN_STATES,
    DuePrecision,
    IjroState,
    LifeSource,
    normalize_person_name,
)
from app.domain.programs import PaceVerdict, pace, year_end
from app.domain.tasks import TITLE_MAX_LENGTH

NEAR_DUE_DAYS = 30
"""«Близкий срок» вопроса «работает ли ответственный?» (ТЗ 5): срок не дальше месяца или
уже прошёл. Порога в ТЗ нет — допущение V36; в справочник порогов уйдёт по ответу."""

INTERIM_AFTER_DAYS = 92
"""Промежуточный срок — у поручения длиннее трёх месяцев (ТЗ 3.3, V3)."""

TASK_LEAD_WORKDAYS = 3
"""«Разложить на задачу»: срок задачи — за три рабочих дня до срока поручения (V34)."""

CHRONIC_EXTENSIONS = 2
"""«Продлевали ≥ 2» — хроническое поручение (ТЗ 5)."""

TEXT_MAX_LENGTH = 4000
"""Комментарий отметки, проблема и предложение: абзац доклада, а не документ."""


class Question(StrEnum):
    """Двенадцать вопросов раздела (V31). Порядок объявления — порядок на телефоне."""

    BURNING = "burning"
    SILENT = "silent"
    FOREIGN = "foreign"
    AWAITING = "awaiting"
    RETURNED = "returned"
    EXTENSION_REQUESTED = "extension_requested"
    REPORT_UP = "report_up"
    WITHOUT_TASKS = "without_tasks"
    CHRONIC = "chronic"
    YEAR_END = "year_end"
    LAST_BATCH = "last_batch"
    DOCUMENTS = "documents"


# ---------------------------------------------------------------------------
# Признак жизни, промежуточный срок, задача из поручения
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LifeSign:
    on: date
    source: LifeSource


def sign_of_life(events: Iterable[LifeSign]) -> LifeSign | None:
    """Самое свежее из событий (ТЗ 4); `None` — движения не было с привоза.

    При равных датах побеждает событие, названное раньше: отметка, затем задача, затем
    SETA. Порядок нужен, чтобы подпись «по отметке» не менялась от того, в каком порядке
    база отдала строки; SETA последней — при равенстве подпись называет то, что внесли мы.
    """
    best: LifeSign | None = None
    for event in events:
        if best is None or event.on > best.on:
            best = event
    return best


def quiet_days(sign: LifeSign | None, *, first_seen_on: date, today: date) -> int:
    """Дней тишины: от последнего признака жизни, а без него — от появления в реестре.

    Без второй половины поручение, по которому с привоза не было ни одного события,
    считалось бы не молчащим, а «без данных» — и именно оно выпадало бы из вопроса.
    """
    return (today - (sign.on if sign else first_seen_on)).days


def interim_on(*, first_seen_on: date, due_on: date | None) -> date | None:
    """Середина срока, если срок длиннее трёх месяцев (ТЗ 3.3, V3)."""
    if due_on is None:
        return None
    length = (due_on - first_seen_on).days
    if length <= INTERIM_AFTER_DAYS:
        return None
    return first_seen_on + timedelta(days=round(length / 2))


def workdays_before(day: date, count: int) -> date:
    """Дата за `count` рабочих дней до `day`: суббота и воскресенье не в счёт.

    Праздники не учитываются: производственного календаря в системе нет, а ошибка на день
    в сторону «раньше» безопаснее для срока подготовки сведений.
    """
    current = day
    left = count
    while left > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            left -= 1
    return current


_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def task_title(content: str) -> str:
    """Название задачи из поручения — первая фраза содержания (V34).

    Поручение — один абзац в четыреста знаков; первая фраза почти всегда называет само
    действие («…ишлаб чиқилсин»). Длиннее столбца задачи не бывает: обрезается по слову.
    """
    first = _SENTENCE_END.split(content.strip(), maxsplit=1)[0].rstrip(".!? ")
    if len(first) <= TITLE_MAX_LENGTH:
        return first
    cut = first[: TITLE_MAX_LENGTH - 1].rsplit(" ", 1)[0]
    return f"{cut}…"


def task_due(due_on: date | None, precision: DuePrecision) -> date | None:
    """Срок задачи — за три рабочих дня до срока поручения; без дня у срока — пусто (V34)."""
    if due_on is None or precision is not DuePrecision.EXACT:
        return None
    return workdays_before(due_on, TASK_LEAD_WORKDAYS)


_INITIALS = re.compile(r"\b\w\.")


def suggest_people(raw: str, people: Sequence[tuple[uuid.UUID, str]]) -> list[uuid.UUID]:
    """Кого предложить по написанию из таблицы: «Это Каримов А.?» (ТЗ 7).

    Только предложение: совпадение по фамилии, без инициалов. Склеивать написания
    алгоритмом нельзя (CLAUDE.md, `Ш. Арибжанов` — не `А. Арибжанов`), поэтому
    подтверждает человек, и запоминается его выбор, а не это правило.
    """
    surname = normalize_person_name(_INITIALS.sub(" ", raw)).strip()
    if not surname:
        return []
    return [
        person_id for person_id, name in people if normalize_person_name(name).startswith(surname)
    ]


def _clean(text: str | None, *, what: str) -> str | None:
    value = (text or "").strip()
    if len(value) > TEXT_MAX_LENGTH:
        raise RuleViolationError(f"{what} длиннее {TEXT_MAX_LENGTH} знаков")
    return value or None


def clean_mark(
    *, promised_on: date | None, comment: str | None, today: date
) -> tuple[date | None, str | None]:
    """Контрольная отметка, пригодная к записи: обещание — не в прошлом.

    «Обещал к вчера» — не обещание, а просрочка: её покажет ступень, а отметка с такой
    датой только спрятала бы её за словом «делает».
    """
    if promised_on is not None and promised_on < today:
        raise RuleViolationError("Дата обещания уже прошла")
    return promised_on, _clean(comment, what="Комментарий")


def clean_problem(problem: str | None, proposal: str | None) -> tuple[str | None, str | None]:
    """Проблема и предложение (ТЗ 3.3). Предложения без проблемы не бывает.

    Пустая проблема снимает и предложение: справка «что докладывать наверх» собирается по
    проблеме, и предложение без неё повисло бы в карточке, никуда не попадая.
    """
    cleaned = _clean(problem, what="Проблема")
    if cleaned is None:
        return None, None
    return cleaned, _clean(proposal, what="Предложение")


# ---------------------------------------------------------------------------
# Строка реестра и ответы
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Line:
    """Строка реестра со всем, из чего считаются ответы. Ступень — уже посчитанная."""

    id: uuid.UUID
    document_id: uuid.UUID
    state: IjroState
    state_changed_on: date
    step: Attention | None
    """Ступень лестницы; `None` — по плану, сдано или снято с контроля."""

    deviation: int
    due_on: date | None
    due_precision: DuePrecision
    original_due_on: date | None
    extensions: int
    """Сколько раз продлевали — только продления, без исправленных дат."""

    extension_requested: bool
    responsible_person_id: uuid.UUID | None
    responsible_raw: str
    lead_organization_id: uuid.UUID | None
    is_co_executor: bool
    quiet: int
    """Дней тишины — см. `quiet_days`."""

    has_problem: bool
    problem_updated_on: date | None
    tasks: int
    first_seen_on: date

    @property
    def is_open(self) -> bool:
        return self.state in OPEN_STATES


@dataclass(frozen=True, slots=True)
class Oldest:
    id: uuid.UUID
    days: int


@dataclass(frozen=True, slots=True)
class PersonLoad:
    person_id: uuid.UUID | None
    responsible_raw: str
    overdue: int = 0
    burning: int = 0


@dataclass(frozen=True, slots=True)
class OrganizationGroup:
    organization_id: uuid.UUID
    rows: tuple[uuid.UUID, ...]

    @property
    def count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True, slots=True)
class SilentWorst:
    id: uuid.UUID
    person_id: uuid.UUID | None
    responsible_raw: str
    days: int


@dataclass(frozen=True, slots=True)
class DocumentShare:
    document_id: uuid.UUID
    done: int
    total: int


@dataclass(frozen=True, slots=True)
class ChronicSample:
    id: uuid.UUID
    original_due_on: date
    due_on: date
    extensions: int


@dataclass(frozen=True, slots=True)
class BatchEffect:
    """Что изменила последняя применённая таблица — из отчёта партии привоза."""

    batch_id: uuid.UUID
    created: tuple[uuid.UUID, ...] = ()
    changed: tuple[uuid.UUID, ...] = ()
    vanished: int = 0
    pending_extensions: int = 0


@dataclass(frozen=True, slots=True)
class Answer:
    """Ответ на вопрос: число или фраза и **те же строки**, что считались (ТЗ 5).

    Одна форма на двенадцать вопросов: у каждого свои поля, но список под действием всегда
    `rows` — и число в виджете, и список на экране получаются одним вычислением.
    """

    key: Question
    rows: tuple[uuid.UUID, ...]
    count: int = 0
    burning: int = 0
    overdue: int = 0
    oldest: Oldest | None = None
    by_person: tuple[PersonLoad, ...] = ()
    organizations: tuple[OrganizationGroup, ...] = ()
    silent_worst: SilentWorst | None = None
    document_worst: DocumentShare | None = None
    chronic_sample: ChronicSample | None = None
    upcoming: int = 0
    closed: int = 0
    window_days: int = 0
    min_closed: int = 0
    verdict: PaceVerdict | None = None
    freshest_on: date | None = None
    total: int = 0
    batch: BatchEffect | None = None


@dataclass(frozen=True, slots=True)
class Limits:
    """Пороги, по которым считаются ответы, — экран называет правило рядом с числом."""

    quiet_days: int
    near_due_days: int
    pace_window_days: int
    min_closed_for_pace: int


@dataclass(frozen=True, slots=True)
class WallCell:
    id: uuid.UUID
    band: str | None
    state: IjroState
    step: Attention | None


@dataclass(frozen=True, slots=True)
class WallDocument:
    """«Как исполнен документ целиком?» (ТЗ 5): сдано X из Y и кого вызвать с отчётом."""

    document_id: uuid.UUID
    done: int
    total: int
    cells: tuple[WallCell, ...]
    call_for_report: tuple[uuid.UUID, int] | None = field(default=None)


def _ids(lines: Iterable[Line]) -> tuple[uuid.UUID, ...]:
    return tuple(line.id for line in lines)


def _oldest(lines: Sequence[Line], days: dict[uuid.UUID, int]) -> Oldest | None:
    if not lines:
        return None
    top = max(lines, key=lambda line: days[line.id])
    return Oldest(id=top.id, days=days[top.id])


def wall(
    lines: Sequence[Line],
    documents: Sequence[uuid.UUID],
    bands: dict[uuid.UUID, str | None],
    band_order: dict[uuid.UUID, str],
) -> list[WallDocument]:
    """Стена документов: клетка на пункт в порядке пунктов, сдано — не открытое."""
    result: list[WallDocument] = []
    for document_id in documents:
        own = sorted(
            (line for line in lines if line.document_id == document_id),
            key=lambda line: (band_order[line.id], str(line.id)),
        )
        open_lines = [line for line in own if line.is_open]
        load: dict[uuid.UUID, int] = {}
        for line in open_lines:
            if line.responsible_person_id is not None:
                load[line.responsible_person_id] = load.get(line.responsible_person_id, 0) + 1
        # Больше всего открытых — первым; при равенстве — по идентификатору, чтобы ответ не
        # менялся от порядка строк в базе.
        call = min(load.items(), key=lambda pair: (-pair[1], str(pair[0])), default=None)
        result.append(
            WallDocument(
                document_id=document_id,
                done=len(own) - len(open_lines),
                total=len(own),
                cells=tuple(
                    WallCell(id=line.id, band=bands[line.id], state=line.state, step=line.step)
                    for line in own
                ),
                call_for_report=call,
            )
        )
    return result


def answers(
    lines: Sequence[Line],
    *,
    today: date,
    limits: Limits,
    documents: Sequence[WallDocument],
    batch: BatchEffect | None,
) -> list[Answer]:
    """Двенадцать ответов в порядке `Question`. `lines` — в порядке лестницы."""
    open_lines = [line for line in lines if line.is_open]
    known = {line.id for line in lines}

    def burning() -> Answer:
        hot = [line for line in open_lines if line.step in {Attention.OVERDUE, Attention.BURNING}]
        overdue = [line for line in hot if line.step is Attention.OVERDUE]
        people: dict[tuple[uuid.UUID | None, str], PersonLoad] = {}
        for line in hot:
            # Несопоставленное написание — отдельный «человек»: торопить его всё равно надо.
            key = (
                line.responsible_person_id,
                "" if line.responsible_person_id else line.responsible_raw,
            )
            entry = people.get(key) or PersonLoad(line.responsible_person_id, line.responsible_raw)
            people[key] = PersonLoad(
                entry.person_id,
                entry.responsible_raw,
                overdue=entry.overdue + (line.step is Attention.OVERDUE),
                burning=entry.burning + (line.step is Attention.BURNING),
            )
        return Answer(
            key=Question.BURNING,
            rows=_ids(hot),
            burning=len(hot) - len(overdue),
            overdue=len(overdue),
            oldest=_oldest(overdue, {line.id: line.deviation for line in overdue}),
            by_person=tuple(
                sorted(
                    people.values(),
                    key=lambda each: (-each.overdue, -each.burning, each.responsible_raw),
                )
            ),
        )

    def silent() -> Answer:
        quiet = [
            line
            for line in open_lines
            if line.due_on is not None
            and (line.due_on - today).days <= limits.near_due_days
            and line.quiet > limits.quiet_days
        ]
        quiet.sort(key=lambda line: -line.quiet)
        top = quiet[0] if quiet else None
        return Answer(
            key=Question.SILENT,
            rows=_ids(quiet),
            count=len(quiet),
            silent_worst=(
                SilentWorst(top.id, top.responsible_person_id, top.responsible_raw, top.quiet)
                if top
                else None
            ),
        )

    def foreign() -> Answer:
        # Сорвётся из-за чужого ведомства: мы соисполнитель, и строка уже на лестнице.
        # «Ждёт решения» не в счёт: его держит руководитель, а не ведомство.
        rows = [
            line
            for line in open_lines
            if line.is_co_executor
            and line.lead_organization_id is not None
            and line.step is not None
            and line.step is not Attention.AWAITING_DECISION
        ]
        groups: dict[uuid.UUID, list[uuid.UUID]] = {}
        for line in rows:
            assert line.lead_organization_id is not None
            groups.setdefault(line.lead_organization_id, []).append(line.id)
        return Answer(
            key=Question.FOREIGN,
            rows=_ids(rows),
            count=len(rows),
            organizations=tuple(
                sorted(
                    (OrganizationGroup(org, tuple(ids)) for org, ids in groups.items()),
                    key=lambda group: (-group.count, str(group.organization_id)),
                )
            ),
        )

    def awaiting() -> Answer:
        rows = [line for line in open_lines if line.step is Attention.AWAITING_DECISION]
        return Answer(
            key=Question.AWAITING,
            rows=_ids(rows),
            count=len(rows),
            oldest=_oldest(rows, {line.id: line.deviation for line in rows}),
        )

    def returned() -> Answer:
        rows = [line for line in lines if line.state is IjroState.RETURNED]
        return Answer(
            key=Question.RETURNED,
            rows=_ids(rows),
            count=len(rows),
            oldest=_oldest(rows, {line.id: (today - line.state_changed_on).days for line in rows}),
        )

    def extension_requested() -> Answer:
        rows = [line for line in open_lines if line.extension_requested]
        return Answer(key=Question.EXTENSION_REQUESTED, rows=_ids(rows), count=len(rows))

    def report_up() -> Answer:
        rows = [line for line in open_lines if line.has_problem]
        dates = [line.problem_updated_on for line in rows if line.problem_updated_on]
        return Answer(
            key=Question.REPORT_UP,
            rows=_ids(rows),
            count=len(rows),
            freshest_on=max(dates, default=None),
        )

    def without_tasks() -> Answer:
        # Полнота по ADR-0033: открытые с точным сроком, у которых нет ни одной задачи.
        exact = [
            line
            for line in open_lines
            if line.due_precision is DuePrecision.EXACT and line.due_on is not None
        ]
        rows = [line for line in exact if line.tasks == 0]
        return Answer(
            key=Question.WITHOUT_TASKS, rows=_ids(rows), count=len(rows), total=len(exact)
        )

    def chronic() -> Answer:
        rows = [line for line in open_lines if line.extensions >= CHRONIC_EXTENSIONS]
        top = rows[0] if rows else None
        return Answer(
            key=Question.CHRONIC,
            rows=_ids(rows),
            count=len(rows),
            chronic_sample=(
                ChronicSample(top.id, top.original_due_on, top.due_on, top.extensions)
                if top and top.original_due_on and top.due_on
                else None
            ),
        )

    def year_end_answer() -> Answer:
        # «Хватит ли сил на декабрь?» — тот же темп, что у «успеваем?» программ (ТЗ 4):
        # закрытое за окно против наступающего до конца года.
        last = year_end(today)
        upcoming = [
            line for line in open_lines if line.due_on is not None and today <= line.due_on <= last
        ]
        closed = sum(
            1
            for line in lines
            if not line.is_open and (today - line.state_changed_on).days <= limits.pace_window_days
        )
        verdict = pace(
            today=today,
            due_on=last,
            closed=closed,
            closed_tasks=closed,
            remaining=len(upcoming),
            min_closed_tasks=limits.min_closed_for_pace,
            window_days=limits.pace_window_days,
        ).verdict
        return Answer(
            key=Question.YEAR_END,
            # «Начинать заранее»: из наступающих — не начатые.
            rows=_ids(line for line in upcoming if line.state is IjroState.NOT_STARTED),
            upcoming=len(upcoming),
            closed=closed,
            window_days=limits.pace_window_days,
            min_closed=limits.min_closed_for_pace,
            verdict=verdict,
        )

    def last_batch() -> Answer:
        if batch is None:
            return Answer(key=Question.LAST_BATCH, rows=())
        return Answer(
            key=Question.LAST_BATCH,
            rows=tuple(each for each in (*batch.created, *batch.changed) if each in known),
            batch=batch,
        )

    def documents_answer() -> Answer:
        candidates = [each for each in documents if each.total > 0 and each.done < each.total]
        worst = min(
            candidates,
            key=lambda each: (each.done / each.total, str(each.document_id)),
            default=None,
        )
        if worst is None:
            return Answer(key=Question.DOCUMENTS, rows=())
        return Answer(
            key=Question.DOCUMENTS,
            rows=_ids(line for line in open_lines if line.document_id == worst.document_id),
            document_worst=DocumentShare(worst.document_id, worst.done, worst.total),
        )

    rules = {
        Question.BURNING: burning,
        Question.SILENT: silent,
        Question.FOREIGN: foreign,
        Question.AWAITING: awaiting,
        Question.RETURNED: returned,
        Question.EXTENSION_REQUESTED: extension_requested,
        Question.REPORT_UP: report_up,
        Question.WITHOUT_TASKS: without_tasks,
        Question.CHRONIC: chronic,
        Question.YEAR_END: year_end_answer,
        Question.LAST_BATCH: last_batch,
        Question.DOCUMENTS: documents_answer,
    }
    return [rules[key]() for key in Question]
