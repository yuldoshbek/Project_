"""Сервис показателей: единственное место, откуда берутся сигналы.

Это инвариант 2 в виде кода. Экран, отчёт, уведомление и сценарий «что если» берут числа
только отсюда — два источника расчёта разошлись бы, и доверия не было бы ни к одному.
Проверяется тестом: числа утренней сводки совпадают с лестницей на тех же данных.

**Как устроен.** Три шага, каждый в своём слое:

1. пороги — из справочника (ТЗ 3.9), одним запросом;
2. снимок незавершённых записей — `app.repos.attention`, только чтение;
3. расчёт — `app.domain.attention.build_ladder`, чистая функция.

**«Что если» — тот же путь с подменённым снимком.** `what_if` получает новые сроки,
применяет их к снимку в памяти и считает лестницу тем же кодом. Записывать в базу ему
нечем по устройству: изменения не касаются ни одной модели, только копий строк снимка.
Применить «что если» — отдельное действие сервиса правки, которое появится вместе с
экраном (критерий 3 блока 1).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import (
    Attention,
    DueChanges,
    Holder,
    Item,
    Ladder,
    Row,
    build_ladder,
    with_due_changes,
)
from app.domain.attention import holders as holders_of
from app.domain.calendar import CalendarKind, HotDay
from app.domain.calendar import hot_days as hot_days_of
from app.domain.calendar import window as hot_window_of
from app.domain.dictionaries import ProjectStatus, SettingKey, TaskStatus
from app.domain.ideas import Answer as IdeasAnswer
from app.domain.ideas import Waiting as IdeaWaiting
from app.domain.ideas import awaiting as ideas_awaiting_of
from app.domain.ijro_control import NEAR_DUE_DAYS
from app.domain.ijro_control import Answer as IjroAnswer
from app.domain.ijro_control import BatchEffect as IjroBatch
from app.domain.ijro_control import Limits as IjroLimits
from app.domain.ijro_control import Line as IjroLine
from app.domain.ijro_control import WallDocument as IjroWall
from app.domain.ijro_control import answers as ijro_answers_of
from app.domain.ijro_control import wall as ijro_wall_of
from app.domain.interaction import (
    DEFAULT_SLEEPING_DAYS,
    AgreementLine,
    LetterLine,
    OrganizationSpeed,
)
from app.domain.interaction import Answer as InteractionAnswer
from app.domain.interaction import answers as interaction_answers_of
from app.domain.programs import PACE_WINDOW_DAYS, Pace, days_left, in_window, window_start
from app.domain.programs import pace as pace_of
from app.domain.projects import (
    DEFAULT_IMPEDIMENT_STALE_DAYS,
    impediment_is_stale,
    project_lag,
    project_readiness,
)
from app.domain.pult import (
    DECISIONS,
    MILESTONES,
    PROJECTS,
    TASKS,
    AuditEntry,
    DeadlineMoves,
    PeriodTotals,
    due_shift,
)
from app.domain.pult import deadline_moves as moves_of
from app.domain.pult import period_totals as totals_of
from app.domain.tasks import Horizon, horizon_of
from app.repos import attention as snapshot
from app.repos import pult as read_model
from app.services.dictionaries import load_settings

DEFAULT_BURN_DAYS = 7
DEFAULT_QUIET_DAYS = 14
DEFAULT_MIN_CLOSED_FOR_PACE = 10
DEFAULT_HOT_DAY_THRESHOLD = 3
DEFAULT_HOT_WINDOW_DAYS = 28
DEFAULT_MIN_LETTERS_FOR_SPEED = 5

MOVES_PERIOD_DAYS = 30
"""«Держим ли мы свои сроки?» — за месяц: короче не видно привычки переносить, длиннее
в ответ попадают переносы, о которых уже договорились и забыли."""

MOVES_TOP = 5
"""Сколько самых переносимых записей показать: на телефоне больше пяти не читают."""


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Пороги лестницы, прочитанные один раз на весь расчёт."""

    burn_days: int
    quiet_days: int
    impediment_stale_days: int = DEFAULT_IMPEDIMENT_STALE_DAYS
    min_closed_for_pace: int = DEFAULT_MIN_CLOSED_FOR_PACE
    hot_day_threshold: int = DEFAULT_HOT_DAY_THRESHOLD
    hot_window_days: int = DEFAULT_HOT_WINDOW_DAYS
    sleeping_days: int = DEFAULT_SLEEPING_DAYS
    min_letters_for_speed: int = DEFAULT_MIN_LETTERS_FOR_SPEED


async def load_thresholds(session: AsyncSession) -> Thresholds:
    """Пороги из справочника одним запросом. Значения по умолчанию — на пустую таблицу."""
    stored = await load_settings(session)
    return Thresholds(
        burn_days=int(stored.get(SettingKey.BURN_DAYS, DEFAULT_BURN_DAYS)),
        quiet_days=int(stored.get(SettingKey.QUIET_DAYS, DEFAULT_QUIET_DAYS)),
        impediment_stale_days=int(
            stored.get(SettingKey.IMPEDIMENT_STALE_DAYS, DEFAULT_IMPEDIMENT_STALE_DAYS)
        ),
        min_closed_for_pace=int(
            stored.get(SettingKey.MIN_CLOSED_FOR_PACE, DEFAULT_MIN_CLOSED_FOR_PACE)
        ),
        hot_day_threshold=int(stored.get(SettingKey.HOT_DAY_THRESHOLD, DEFAULT_HOT_DAY_THRESHOLD)),
        hot_window_days=int(stored.get(SettingKey.HOT_WINDOW_DAYS, DEFAULT_HOT_WINDOW_DAYS)),
        sleeping_days=int(stored.get(SettingKey.SLEEPING_DAYS, DEFAULT_SLEEPING_DAYS)),
        min_letters_for_speed=int(
            stored.get(SettingKey.MIN_LETTERS_FOR_SPEED, DEFAULT_MIN_LETTERS_FOR_SPEED)
        ),
    )


@dataclass(frozen=True, slots=True)
class Progress:
    """Где проект по плану: готовность и отставание — одна пара на все экраны."""

    readiness: int
    lag_days: int


@dataclass(frozen=True, slots=True)
class Work:
    """Вехи и задачи, по которым считаются готовность, отставание и «успеваем?»."""

    passed_milestones: int = 0
    total_milestones: int = 0
    done_tasks: int = 0
    total_tasks: int = 0

    @property
    def closed(self) -> int:
        return self.passed_milestones + self.done_tasks

    @property
    def remaining(self) -> int:
        return self.total_milestones + self.total_tasks - self.closed

    def __add__(self, other: Work) -> Work:
        return Work(
            passed_milestones=self.passed_milestones + other.passed_milestones,
            total_milestones=self.total_milestones + other.total_milestones,
            done_tasks=self.done_tasks + other.done_tasks,
            total_tasks=self.total_tasks + other.total_tasks,
        )


class _Mark(Protocol):
    @property
    def is_passed(self) -> bool: ...

    @property
    def passed_on(self) -> date | None: ...


class _Counted(Protocol):
    """Строка проекта из read-модели (`app.repos.projects.ProjectRow`)."""

    @property
    def id(self) -> uuid.UUID: ...

    @property
    def status(self) -> str: ...

    @property
    def due_on(self) -> date: ...

    @property
    def marks(self) -> Sequence[_Mark]: ...

    @property
    def done_tasks(self) -> int: ...

    @property
    def total_tasks(self) -> int: ...


def _own(row: _Counted) -> Work:
    return Work(
        passed_milestones=sum(1 for mark in row.marks if mark.is_passed),
        total_milestones=len(row.marks),
        done_tasks=row.done_tasks,
        total_tasks=row.total_tasks,
    )


def work_of(row: _Counted, children: Iterable[_Counted] = ()) -> Work:
    """Вехи и задачи проекта — у программы вместе с подпроектами (допущение V13).

    Программу передают с её подпроектами: раздел «Программы» отвечает, где мы по программе
    целиком, а карточка той же записи в «Проектах» обязана показать тот же процент
    (инвариант 2). Готовность, отставание и «успеваем?» одной карточки считаются по одному
    набору, иначе «готово 44 %» спорит с «осталось 27».

    Закрытый подпроект своё не держит. Завершённый считается сделанным целиком — как у
    `project_readiness`: «завершён» — последнее слово помощника. У отменённого остаётся
    только сделанное: несделанное не сделают, и в знаменателе оно навсегда держало бы
    программу недоделанной — ровно то, что «урезать объём» и снимает.
    """
    total = _own(row)
    for child in children:
        counts = _own(child)
        status = ProjectStatus(child.status)
        if status is ProjectStatus.DONE:
            counts = Work(
                passed_milestones=counts.total_milestones,
                total_milestones=counts.total_milestones,
                done_tasks=counts.total_tasks,
                total_tasks=counts.total_tasks,
            )
        elif status is ProjectStatus.CANCELLED:
            counts = Work(
                passed_milestones=counts.passed_milestones,
                total_milestones=counts.passed_milestones,
                done_tasks=counts.done_tasks,
                total_tasks=counts.done_tasks,
            )
        total += counts
    return total


def progress(
    *,
    status: ProjectStatus,
    started_on: date,
    due_on: date,
    today: date,
    work: Work,
) -> Progress:
    """Готовность и отставание проекта (ТЗ 3.1, 4).

    Отсюда их берут карточка, таблица, таймлайн, «что если» и «Программы»: отставание при
    другом сроке считается этой же функцией, а не второй формулой рядом с экраном.
    """
    ready = project_readiness(
        status=status,
        passed_milestones=work.passed_milestones,
        total_milestones=work.total_milestones,
        done_tasks=work.done_tasks,
        total_tasks=work.total_tasks,
    )
    return Progress(
        readiness=ready,
        lag_days=project_lag(
            status=status, started_on=started_on, due_on=due_on, today=today, readiness_pct=ready
        ),
    )


def countdown(*, due_on: date, today: date) -> int:
    """Отсчёт до даты программы — календарные дни по Ташкенту (ТЗ 11)."""
    return days_left(due_on=due_on, today=today)


def pace_window(today: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """Окно темпа моментами: с начала первого дня окна до конца сегодня, по Ташкенту.

    То же правило, что у вех (`domain.programs.in_window`): закрытое строго после последнего
    дня до окна и не позже сегодня. Задача, закрытая сегодня вечером, — уже темп.
    """
    since = datetime.combine(window_start(today) + timedelta(days=1), time(), zone)
    until = datetime.combine(today + timedelta(days=1), time(), zone)
    return since, until


def program_pace(
    row: _Counted,
    children: Sequence[_Counted],
    *,
    closed_tasks: Mapping[uuid.UUID, int],
    today: date,
    thresholds: Thresholds,
) -> Pace | None:
    """«Успеваем ли к дате программы?» (ТЗ 4, 5; допущение V13). У закрытой — не спрашивают.

    Закрыто за окно — задачи программы и всех её подпроектов (`closed_tasks` — по окну
    `pace_window`) и вехи, пройденные в окне: темп — это работа, сделанная за три месяца,
    даже если подпроект с тех пор закрыли. Осталось — тот же набор, что у готовности
    (`work_of`). Порог «мало данных» — справочник (ТЗ 3.9).
    """
    if ProjectStatus(row.status).is_terminal:
        return None
    works = [row, *children]
    tasks = sum(closed_tasks.get(work.id, 0) for work in works)
    marks = sum(
        1
        for work in works
        for mark in work.marks
        if mark.is_passed and in_window(mark.passed_on, today=today)
    )
    return pace_of(
        today=today,
        due_on=row.due_on,
        closed=tasks + marks,
        closed_tasks=tasks,
        remaining=work_of(row, children).remaining,
        min_closed_tasks=thresholds.min_closed_for_pace,
    )


def hot_window(today: date, thresholds: Thresholds) -> tuple[date, date]:
    """Окно ответа «где неделя перегружена?» — с сегодняшнего, длина из справочника (V15)."""
    return hot_window_of(today, thresholds.hot_window_days)


def hot_days(
    open_dates: Iterable[tuple[date, CalendarKind]],
    *,
    since: date,
    until: date,
    today: date,
    thresholds: Thresholds,
) -> list[HotDay]:
    """Горячие дни с `since` по `until` — порог из справочника (ТЗ 5, V15).

    Прошедшие дни горячими не бывают: несделанное там уже «срок прошёл», и начало
    поднимается до сегодняшнего здесь, а не у каждого вызова.
    """
    return hot_days_of(
        open_dates,
        since=max(since, today),
        until=until,
        threshold=thresholds.hot_day_threshold,
    )


def impediment_stale(*, updated_on: date | None, today: date, thresholds: Thresholds) -> bool:
    """Устарела ли строка «что мешает» — порог из справочника (ТЗ 3.9), по дням Ташкента."""
    return impediment_is_stale(
        updated_on=updated_on, today=today, stale_days=thresholds.impediment_stale_days
    )


async def ladder(
    session: AsyncSession,
    *,
    today: date,
    zone: ZoneInfo,
    thresholds: Thresholds | None = None,
) -> Ladder:
    """Лестница внимания по всем разделам — то, что показывает Пульт."""
    limits = thresholds or await load_thresholds(session)
    items = await snapshot.load_items(session, zone=zone, sleeping_days=limits.sleeping_days)
    return build_ladder(
        items, today=today, burn_days=limits.burn_days, quiet_days=limits.quiet_days
    )


def steps(items: Iterable[Item], *, today: date, thresholds: Thresholds) -> dict[uuid.UUID, Row]:
    """Ступени отдельных записей — тем же `build_ladder`, что строит Пульт.

    Раздел «Ижро» показывает ступень у каждой строки реестра, а не только у тех, что на
    Пульте; считать её второй формулой значило бы рискнуть, что поручение горит на Пульте и
    идёт по плану в своём разделе (инвариант 2). Записи без строки — по плану.
    """
    ladder = build_ladder(
        items, today=today, burn_days=thresholds.burn_days, quiet_days=thresholds.quiet_days
    )
    return {row.entity_id: row for row in ladder.rows}


def interaction_answers(
    letters: Sequence[LetterLine],
    speeds: Sequence[OrganizationSpeed],
    agreements: Sequence[AgreementLine],
    *,
    today: date,
    thresholds: Thresholds,
) -> list[InteractionAnswer]:
    """Четыре ответа «Взаимодействия» (ТЗ 5) — по строкам в порядке лестницы."""
    return interaction_answers_of(
        letters, speeds, agreements, today=today, min_letters=thresholds.min_letters_for_speed
    )


def ijro_limits(thresholds: Thresholds) -> IjroLimits:
    """Пороги вопросов Ижро: тишина и темп — из справочника, «близкий срок» — V36."""
    return IjroLimits(
        quiet_days=thresholds.quiet_days,
        near_due_days=NEAR_DUE_DAYS,
        pace_window_days=PACE_WINDOW_DAYS,
        min_closed_for_pace=thresholds.min_closed_for_pace,
    )


def ijro_wall(
    lines: Sequence[IjroLine],
    documents: Sequence[uuid.UUID],
    bands: dict[uuid.UUID, str | None],
    band_order: dict[uuid.UUID, str],
) -> list[IjroWall]:
    """«Как исполнен документ целиком?» — стена документов (ТЗ 5)."""
    return ijro_wall_of(lines, documents, bands, band_order)


def ijro_answers(
    lines: Sequence[IjroLine],
    *,
    today: date,
    thresholds: Thresholds,
    documents: Sequence[IjroWall],
    batch: IjroBatch | None,
) -> list[IjroAnswer]:
    """Двенадцать ответов раздела «Ижро» (V31) — по строкам в порядке лестницы."""
    return ijro_answers_of(
        lines, today=today, limits=ijro_limits(thresholds), documents=documents, batch=batch
    )


def ideas_awaiting(ideas: Iterable[IdeaWaiting], *, today: date) -> IdeasAnswer:
    """«Что ждёт моего „да“?» — идеи на рассмотрении, дольше всех ждущая первой (V46)."""
    return ideas_awaiting_of(ideas, today)


def holders(ladder: Ladder) -> list[Holder]:
    """«Кто держит» — по строкам той же лестницы, а не отдельным подсчётом."""
    return holders_of(ladder.rows)


def due_today(ladder: Ladder, today: date) -> tuple[Row, ...]:
    """«Срок сегодня» утренней сводки — строки лестницы со сроком сегодня, на любой ступени.

    На любой, а не только «горит» (V26): вопрос по вехе, срок которой сегодня, стоит на
    ступени «ждёт решения» — и руководитель должен увидеть его в обоих списках. Нормы
    здесь быть не может: срок сегодня делает строку горящей при любом пороге.
    """
    return tuple(row for row in ladder.rows if row.due_on == today)


async def deadline_moves(
    session: AsyncSession,
    *,
    now: datetime,
    zone: ZoneInfo,
    period_days: int = MOVES_PERIOD_DAYS,
    top: int = MOVES_TOP,
    since: datetime | None = None,
) -> DeadlineMoves:
    """«Держим ли мы свои сроки?»: переносы и суммарный сдвиг за период — по журналу.

    По умолчанию — последние `period_days` до `now`; отчёт передаёт свои границы.
    """
    entries = await read_model.audit_entries(
        session,
        since=since or now - timedelta(days=period_days),
        until=now,
        entity_types=(PROJECTS, MILESTONES, TASKS),
    )
    return moves_of(entries, zone=zone, period_days=period_days, top=top)


def moves_count(entries: Iterable[AuditEntry], *, zone: ZoneInfo) -> int:
    """Сколько раз срок записи переносили позже — за всю её жизнь, по журналу.

    Правило то же, что у «Держим ли мы свои сроки?» (`app.domain.pult.deadline_moves`):
    перенос — сдвиг позже, подтянутый срок переносом не считается. Иначе карточка и Пульт
    назвали бы разное число переносов одной и той же работы.
    """
    count = 0
    for entry in entries:
        shift = due_shift(entry, zone)
        if shift is not None and shift[1] > shift[0]:
            count += 1
    return count


def horizon(*, status: TaskStatus, due_on: date | None, today: date) -> Horizon:
    """«К какому сроку» — группа задачи в списке (раздел «Задачи»)."""
    return horizon_of(status=status, due_on=due_on, today=today)


@dataclass(frozen=True, slots=True)
class Load:
    """«Кто перегружен?» (ТЗ 5) — строка на ответственного."""

    person_id: uuid.UUID
    overdue: int
    burning: int
    open: int


def task_load(
    ladder: Ladder, open_tasks: Iterable[tuple[uuid.UUID, uuid.UUID | None]]
) -> list[Load]:
    """Просрочки и горящие сроки по ответственным — по строкам той же лестницы.

    `open_tasks` — (задача, ответственный) незакрытых задач, которые стоят в лестнице
    (`app.repos.attention` отсекает и задачи закрытых проектов). Число просроченного у
    человека обязано совпадать с числом его просроченных строк в списке — поэтому счёт идёт
    по строкам лестницы, а не отдельным запросом. Первым — у кого больше просрочено, затем
    горит, затем больше работы.
    """
    step = {row.entity_id: row.attention for row in ladder.rows if row.section == "tasks"}
    rows: dict[uuid.UUID, list[int]] = {}
    for task_id, person_id in open_tasks:
        if person_id is None:
            continue
        counts = rows.setdefault(person_id, [0, 0, 0])
        counts[2] += 1
        if step.get(task_id) is Attention.OVERDUE:
            counts[0] += 1
        elif step.get(task_id) is Attention.BURNING:
            counts[1] += 1
    return sorted(
        (
            Load(person_id=person_id, overdue=overdue, burning=burning, open=total)
            for person_id, (overdue, burning, total) in rows.items()
        ),
        key=lambda load: (-load.overdue, -load.burning, -load.open),
    )


async def period_totals(
    session: AsyncSession, *, start: datetime, end: datetime, zone: ZoneInfo
) -> PeriodTotals:
    """Итоги периода для отчёта недели и месяца — по журналу, тем же правилом."""
    entries = await read_model.audit_entries(
        session,
        since=start,
        until=end,
        entity_types=(PROJECTS, MILESTONES, TASKS, DECISIONS),
    )
    return totals_of(entries, zone=zone)


async def what_if(
    session: AsyncSession,
    *,
    today: date,
    zone: ZoneInfo,
    changes: DueChanges,
    thresholds: Thresholds | None = None,
) -> tuple[Ladder, Ladder]:
    """Лестница сейчас и лестница при других сроках — для сравнения на экране.

    Обе считает один код по одному снимку, поэтому разница между ними — ровно следствие
    изменённых сроков, а не второго расчёта.
    """
    limits = thresholds or await load_thresholds(session)
    items = await snapshot.load_items(session, zone=zone, sleeping_days=limits.sleeping_days)

    def count(rows: Iterable[Item]) -> Ladder:
        return build_ladder(
            rows,
            today=today,
            burn_days=limits.burn_days,
            quiet_days=limits.quiet_days,
        )

    return count(items), count(with_due_changes(items, changes))
