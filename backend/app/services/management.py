"""Управление — обход, пороги, справочники, доступ (критерий ТЗ 11, блок 1).

Форма — договор экрана `frontend/src/sections/management/model.ts`, утверждённого
заказчиком 29.09.2026 на вымышленных данных той же формы (CLAUDE.md, цикл блока «экран →
API»). Допущения — V20–V25.

**Числа — из `app.services.metrics`, и больше ниоткуда** (инвариант 2): «сейчас горят
строк» — та же лестница, что у Пульта; «молчит» в обходе — та же ступень; горячие дни —
тот же расчёт, что у Календаря; «мало данных» — тот же «успеваем?», что у Программ.
Предпросмотр порога считает тем же кодом с подставленным значением и ничего не пишет.

**Действия обхода** — существующие правки разделов с их проверками и журналом: закрыть
задачу — тот же `tasks.set_status`, что в карточке; записать «что мешает» — тот же
`projects.set_impediment`. Действие приходит с версией записи, которую видел человек
(инвариант 15), и отмечается в `round_actions` в той же транзакции — ради «сделано на
неделе» (V20).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import QUIET_STEPS, Attention, Ladder
from app.domain.calendar import CalendarKind
from app.domain.clock import local_date
from app.domain.dictionaries import (
    ORGANIZATION_NAME_MAX_LENGTH,
    OrganizationKind,
    ProjectStatus,
    SettingKey,
    TaskStatus,
)
from app.domain.errors import (
    ConflictError,
    NotFoundError,
    RuleViolationError,
    StaleVersionError,
    check_version,
)
from app.domain.management import (
    RECORD_OF,
    THRESHOLD_DEFAULTS,
    DictionaryKind,
    RecordKind,
    RoundAction,
    RoundReason,
    actions_for,
    clean_input,
    clean_name,
    clean_offset,
    clean_threshold,
    moved_due,
    renamed_script,
    threshold_bounds,
    week_start,
)
from app.domain.pult import PROJECTS
from app.repos import calendar as calendar_model
from app.repos import interaction
from app.repos import management as read_model
from app.repos import projects as project_model
from app.repos import pult as pult_model
from app.repos.models import (
    LeaderDecision,
    Milestone,
    Organization,
    Project,
    ProjectTypeMilestone,
    ProjectTypeRef,
    RoundMark,
)
from app.repos.models.dictionaries import DictionaryEntry
from app.services import calendar, decisions, dictionaries, metrics, programs, projects, tasks

# --------------------------------------------------------------------------------------
# Виды экрана
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RoundItemView:
    reason: RoundReason
    target_kind: str
    target_id: uuid.UUID
    record_kind: RecordKind
    record_id: uuid.UUID
    version: int
    title: str
    owner: str | None
    responsible: str | None
    days: int
    actions: list[RoundAction]


@dataclass(frozen=True, slots=True)
class RoundView:
    week_from: date
    week_to: date
    items: list[RoundItemView]
    done: int


@dataclass(frozen=True, slots=True)
class ThresholdView:
    key: SettingKey
    value: Any
    default: Any
    origin: str
    kind: str
    low: int | str | None
    high: int | str | None
    affected: int | None
    version: int


@dataclass(frozen=True, slots=True)
class EntryView:
    id: uuid.UUID
    name: str
    is_active: bool
    used: int
    version: int
    org_kind: str | None
    is_center: bool | None


@dataclass(frozen=True, slots=True)
class GroupView:
    kind: DictionaryKind
    entries: list[EntryView]


@dataclass(frozen=True, slots=True)
class LinkView:
    role: str
    issued_at: datetime | None
    last_login_at: datetime | None


@dataclass(frozen=True, slots=True)
class ManagementView:
    as_of: datetime
    round: RoundView
    thresholds: list[ThresholdView]
    dictionaries: list[GroupView]
    templates: dict[uuid.UUID, list[read_model.StepRow]]
    people: list[tuple[uuid.UUID, str]]
    links: list[LinkView]
    is_demo: bool


# --------------------------------------------------------------------------------------
# Обход
# --------------------------------------------------------------------------------------


def _days(today: date, moment: datetime | date, zone: ZoneInfo) -> int:
    day = local_date(moment, zone) if isinstance(moment, datetime) else moment
    return (today - day).days


async def _round(
    session: AsyncSession,
    *,
    today: date,
    zone: ZoneInfo,
    thresholds: metrics.Thresholds,
    ladder: Ladder,
) -> list[RoundItemView]:
    """Очередь обхода из данных — одна запись один раз, по первой причине (V20)."""
    items: list[RoundItemView] = []
    overdue = await calendar_model.overdue(session, before=today, zone=zone)

    decision_rows = [row for row in overdue if row.kind is CalendarKind.DECISION]
    decision_versions = await read_model.versions(
        session, LeaderDecision, [row.id for row in decision_rows]
    )
    for row in decision_rows:
        # Решение открывает то, по чему оно принято: задачу или проект. Решения по
        # поручениям Ижро — блок 2, у них своей карточки на этом экране нет.
        if row.about is None:
            continue
        about, about_id = row.about
        if about == "task":
            target = ("task", about_id)
        elif row.project_id is not None:
            target = ("project", row.project_id)
        else:
            continue
        items.append(
            RoundItemView(
                reason=RoundReason.DECISION_OVERDUE,
                target_kind=target[0],
                target_id=target[1],
                record_kind=RecordKind.DECISION,
                record_id=row.id,
                version=decision_versions.get(row.id, 1),
                title=row.title or "",
                owner=row.project_title,
                responsible=row.responsible_name,
                days=(today - row.on).days,
                actions=actions_for(RoundReason.DECISION_OVERDUE),
            )
        )

    task_rows = [row for row in overdue if row.kind is CalendarKind.TASK]
    states = await read_model.task_states(session, [row.id for row in task_rows])
    for row in task_rows:
        status, version = states.get(row.id, (TaskStatus.IN_PROGRESS.value, 1))
        items.append(
            RoundItemView(
                reason=RoundReason.TASK_OVERDUE,
                target_kind="task",
                target_id=row.id,
                record_kind=RecordKind.TASK,
                record_id=row.id,
                version=version,
                title=row.title or "",
                owner=row.project_title,
                responsible=row.responsible_name,
                days=(today - row.on).days,
                actions=actions_for(RoundReason.TASK_OVERDUE, task_status=TaskStatus(status)),
            )
        )

    mark_rows = [
        row for row in overdue if row.kind is CalendarKind.MILESTONE and row.project_id is not None
    ]
    mark_versions = await read_model.versions(session, Milestone, [row.id for row in mark_rows])
    for row in mark_rows:
        assert row.project_id is not None
        items.append(
            RoundItemView(
                reason=RoundReason.MILESTONE_PASSED,
                target_kind="project",
                target_id=row.project_id,
                record_kind=RecordKind.MILESTONE,
                record_id=row.id,
                version=mark_versions.get(row.id, 1),
                title=row.title or "",
                owner=row.project_title,
                responsible=row.responsible_name,
                days=(today - row.on).days,
                actions=actions_for(RoundReason.MILESTONE_PASSED),
            )
        )

    for task in await read_model.in_review(session):
        days = _days(today, task.since, zone)
        # Молчание — дольше порога, как у ступени «молчит» (`domain/attention.py`).
        if days > thresholds.quiet_days:
            items.append(_task_item(RoundReason.TASK_REVIEW, task, days))

    for project in await read_model.impediments(session):
        noted = local_date(project.noted_at, zone)
        if metrics.impediment_stale(updated_on=noted, today=today, thresholds=thresholds):
            items.append(
                RoundItemView(
                    reason=RoundReason.IMPEDIMENT_STALE,
                    target_kind="project",
                    target_id=project.id,
                    record_kind=RecordKind.PROJECT,
                    record_id=project.id,
                    version=project.version,
                    title=project.title,
                    owner=None,
                    responsible=project.responsible_name,
                    days=(today - noted).days,
                    actions=actions_for(RoundReason.IMPEDIMENT_STALE),
                )
            )

    # Молчащий проект — та же строка лестницы, что на Пульте: молчит или ждёт чужих, но
    # тишина одна (инвариант 2).
    silent = [
        line for line in ladder.rows if line.section == PROJECTS and line.attention in QUIET_STEPS
    ]
    project_versions = await read_model.versions(
        session, Project, [line.entity_id for line in silent]
    )
    names = await pult_model.people_names(
        session, [line.responsible_person_id for line in silent if line.responsible_person_id]
    )
    for line in silent:
        items.append(
            RoundItemView(
                reason=RoundReason.PROJECT_SILENT,
                target_kind="project",
                target_id=line.entity_id,
                record_kind=RecordKind.PROJECT,
                record_id=line.entity_id,
                version=project_versions.get(line.entity_id, 1),
                title=line.title or "",
                owner=None,
                responsible=names.get(line.responsible_person_id)
                if line.responsible_person_id
                else None,
                days=line.deviation,
                actions=actions_for(RoundReason.PROJECT_SILENT),
            )
        )

    for task in await read_model.unassigned(session):
        days = _days(today, task.since, zone)
        # Заведённая сегодня задача без ответственного — ещё не отставшие данные: её только
        # что записали, ответственного назначат вместе со сроком.
        if days > 0:
            items.append(_task_item(RoundReason.TASK_UNASSIGNED, task, days))

    seen: set[tuple[RecordKind, uuid.UUID]] = set()
    unique: list[RoundItemView] = []
    for item in sorted(items, key=lambda each: (each.reason.rank, -each.days, each.title)):
        key = (item.record_kind, item.record_id)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _task_item(reason: RoundReason, task: read_model.TaskRow, days: int) -> RoundItemView:
    return RoundItemView(
        reason=reason,
        target_kind="task",
        target_id=task.id,
        record_kind=RecordKind.TASK,
        record_id=task.id,
        version=task.version,
        title=task.title,
        owner=task.project_title,
        responsible=task.assignee_name,
        days=days,
        actions=actions_for(reason, task_status=TaskStatus(task.status)),
    )


def _week_moment(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time(0), zone).astimezone(UTC)


# --------------------------------------------------------------------------------------
# Пороги: «сейчас» и предпросмотр
# --------------------------------------------------------------------------------------

_FIELD: dict[SettingKey, str] = {
    SettingKey.BURN_DAYS: "burn_days",
    SettingKey.QUIET_DAYS: "quiet_days",
    SettingKey.IMPEDIMENT_STALE_DAYS: "impediment_stale_days",
    SettingKey.MIN_CLOSED_FOR_PACE: "min_closed_for_pace",
    SettingKey.HOT_DAY_THRESHOLD: "hot_day_threshold",
    SettingKey.HOT_WINDOW_DAYS: "hot_window_days",
    SettingKey.SLEEPING_DAYS: "sleeping_days",
    SettingKey.MIN_LETTERS_FOR_SPEED: "min_letters_for_speed",
}

MAX_WINDOW_DAYS = 90
"""Верхняя граница окна горячих дней в справочнике (`app.seed`): даты читаются на неё один
раз, и предпросмотр любого окна считает по ним же."""


class _Figures:
    """Числа порогов — чтение один раз, расчёт на любое значение без записи."""

    def __init__(self, session: AsyncSession, *, today: date, zone: ZoneInfo) -> None:
        self.session = session
        self.today = today
        self.zone = zone
        self._impediments: list[read_model.ImpedimentRow] | None = None
        self._pace: programs.PaceInputs | None = None
        self._dates: list[tuple[date, CalendarKind]] | None = None

    async def count(
        self, key: SettingKey, thresholds: metrics.Thresholds, ladder: Ladder | None = None
    ) -> int | None:
        if key is SettingKey.SUMMARY_AT:
            return None
        if key in (SettingKey.BURN_DAYS, SettingKey.QUIET_DAYS):
            if ladder is None:
                ladder = await metrics.ladder(
                    self.session, today=self.today, zone=self.zone, thresholds=thresholds
                )
            if key is SettingKey.BURN_DAYS:
                return ladder.count(Attention.BURNING)
            return sum(ladder.count(step) for step in QUIET_STEPS)
        if key is SettingKey.IMPEDIMENT_STALE_DAYS:
            if self._impediments is None:
                self._impediments = await read_model.impediments(self.session)
            return sum(
                1
                for row in self._impediments
                if metrics.impediment_stale(
                    updated_on=local_date(row.noted_at, self.zone),
                    today=self.today,
                    thresholds=thresholds,
                )
            )
        if key is SettingKey.SLEEPING_DAYS:
            agreements = await interaction.agreements(self.session, zone=self.zone)
            return sum(
                1
                for each in agreements
                if (self.today - each.moved_on).days > thresholds.sleeping_days
            )
        if key is SettingKey.MIN_LETTERS_FOR_SPEED:
            replies: dict[uuid.UUID, int] = {}
            for letter in await interaction.letters(self.session):
                if letter.direction.value == "outgoing" and letter.answered_on is not None:
                    replies[letter.organization_id] = replies.get(letter.organization_id, 0) + 1
            return sum(1 for count in replies.values() if count >= thresholds.min_letters_for_speed)
        if key is SettingKey.MIN_CLOSED_FOR_PACE:
            if self._pace is None:
                self._pace = await programs.pace_inputs(
                    self.session, today=self.today, zone=self.zone
                )
            return programs.little_data(self._pace, today=self.today, thresholds=thresholds)
        # Оба порога горячих дней — одно число: горячие дни в окне (`hot_ahead` Календаря).
        if self._dates is None:
            self._dates = await calendar.open_dates(
                self.session,
                since=self.today,
                until=self.today + timedelta(days=MAX_WINDOW_DAYS - 1),
                today=self.today,
                zone=self.zone,
            )
        since, until = metrics.hot_window(self.today, thresholds)
        dates = [(day, kind) for day, kind in self._dates if since <= day <= until]
        return len(
            metrics.hot_days(
                dates, since=since, until=until, today=self.today, thresholds=thresholds
            )
        )


def _key(key: str) -> SettingKey:
    try:
        return SettingKey(key)
    except ValueError as error:
        raise NotFoundError("Такого порога нет") from error


async def preview(
    session: AsyncSession, *, key: str, value: Any, now: datetime, zone: ZoneInfo
) -> int | None:
    """Сколько строк сделает сигналом порог с этим значением — тем же кодом, без записи."""
    setting_key = _key(key)
    row = await read_model.setting(session, setting_key.value)
    if row is None:
        raise NotFoundError("Такого порога нет")
    candidate = clean_threshold(
        value_type=row.value_type, value=value, low=row.min_value, high=row.max_value
    )
    if setting_key is SettingKey.SUMMARY_AT:
        return None
    thresholds = replace(await metrics.load_thresholds(session), **{_FIELD[setting_key]: candidate})
    figures = _Figures(session, today=local_date(now, zone), zone=zone)
    return await figures.count(setting_key, thresholds)


async def save_threshold(session: AsyncSession, *, key: str, value: Any, version: int) -> None:
    """Новое значение порога — с версией и в журнал; меняет сигналы на всех экранах сразу."""
    setting_key = _key(key)
    row = await read_model.setting(session, setting_key.value)
    if row is None:
        raise NotFoundError("Такого порога нет")
    if row.version != version:
        # Своё сообщение, а не общее «запись изменили»: у порога одно значение, и его
        # честнее назвать, чем просить обновить страницу.
        raise StaleVersionError(
            f"Порог изменили, пока вы его правили: сейчас {row.value}. Проверьте и сохраните снова"
        )
    row.value = clean_threshold(
        value_type=row.value_type, value=value, low=row.min_value, high=row.max_value
    )
    await session.flush()


# --------------------------------------------------------------------------------------
# Сборка экрана
# --------------------------------------------------------------------------------------


async def load(
    session: AsyncSession, *, now: datetime, zone: ZoneInfo, is_demo: bool
) -> ManagementView:
    """Весь раздел: обход недели, пороги с числами, справочники, шаблоны, доступ.

    Одна форма ответа для обоих: оба видят всё, роль ограничивает правку (инвариант 13).
    """
    today = local_date(now, zone)
    thresholds = await metrics.load_thresholds(session)
    ladder = await metrics.ladder(session, today=today, zone=zone, thresholds=thresholds)
    monday = week_start(today)

    figures = _Figures(session, today=today, zone=zone)
    threshold_views: list[ThresholdView] = []
    for row in await read_model.settings(session):
        try:
            key = SettingKey(row.key)
        except ValueError:
            continue
        default, origin = THRESHOLD_DEFAULTS[key]
        low, high = threshold_bounds(
            value_type=row.value_type, low=row.min_value, high=row.max_value
        )
        threshold_views.append(
            ThresholdView(
                key=key,
                value=row.value,
                default=default,
                origin=origin.value,
                kind=row.value_type,
                low=low,
                high=high,
                affected=await figures.count(key, thresholds, ladder),
                version=row.version,
            )
        )
    order = list(THRESHOLD_DEFAULTS)
    threshold_views.sort(key=lambda each: order.index(each.key))

    found = await read_model.entries(session)
    used = await read_model.used(session)
    groups = [
        GroupView(
            kind=kind,
            entries=[
                EntryView(
                    id=row.id,
                    name=row.name,
                    is_active=row.is_active,
                    used=used.get(kind, {}).get(row.id, 0),
                    version=row.version,
                    org_kind=row.org_kind,
                    is_center=row.is_center if kind is DictionaryKind.ORGANIZATIONS else None,
                )
                for row in found.get(kind, [])
            ],
        )
        for kind in DictionaryKind
    ]

    return ManagementView(
        as_of=now,
        round=RoundView(
            week_from=monday,
            week_to=monday + timedelta(days=6),
            items=await _round(
                session, today=today, zone=zone, thresholds=thresholds, ladder=ladder
            ),
            done=await read_model.done_since(session, _week_moment(monday, zone)),
        ),
        thresholds=threshold_views,
        dictionaries=groups,
        templates=await read_model.template_steps(session),
        people=await project_model.people(session),
        links=[
            LinkView(role=row.role, issued_at=row.issued_at, last_login_at=row.last_login_at)
            for row in await read_model.links(session)
        ],
        is_demo=is_demo,
    )


# --------------------------------------------------------------------------------------
# Действия обхода
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RoundStep:
    reason: RoundReason
    record_kind: RecordKind
    record_id: uuid.UUID
    action: RoundAction
    version: int
    input: str | None


async def act(
    session: AsyncSession,
    *,
    step: RoundStep,
    now: datetime,
    zone: ZoneInfo,
) -> None:
    """Действие обхода — правкой раздела; пункт уйдёт сам, когда данные поправлены."""
    if RECORD_OF[step.reason] is not step.record_kind:
        raise RuleViolationError("Эта причина обхода — про другую запись")
    if step.action not in actions_for(step.reason):
        raise RuleViolationError("У этого пункта обхода нет такого действия")
    text = clean_input(step.action, step.input)
    today = local_date(now, zone)
    action, record_id, version = step.action, step.record_id, step.version

    if action is RoundAction.DECISION_DONE:
        await decisions.complete(session, decision_id=record_id, version=version, today=today)
    elif action is RoundAction.MOVE_WEEK:
        due = moved_due(today)
        if step.record_kind is RecordKind.DECISION:
            await decisions.move_due(session, decision_id=record_id, due_on=due, version=version)
        elif step.record_kind is RecordKind.TASK:
            await tasks.shift_due(
                session, task_id=record_id, due_on=due, version=version, zone=zone
            )
        else:
            await projects.move_milestone(
                session, milestone_id=record_id, due_on=due, version=version
            )
    elif action in (RoundAction.TASK_DONE, RoundAction.TASK_CANCEL, RoundAction.TASK_BACK):
        status = {
            RoundAction.TASK_DONE: TaskStatus.DONE,
            RoundAction.TASK_CANCEL: TaskStatus.CANCELLED,
            RoundAction.TASK_BACK: TaskStatus.IN_PROGRESS,
        }[action]
        await tasks.set_status(session, task_id=record_id, status=status, version=version, now=now)
    elif action is RoundAction.MILESTONE_PASSED:
        await projects.pass_milestone(session, milestone_id=record_id, version=version, today=today)
    elif action in (RoundAction.IMPEDIMENT_CONFIRM, RoundAction.IMPEDIMENT_CLEAR, RoundAction.NOTE):
        if action is RoundAction.IMPEDIMENT_CONFIRM:
            project = await session.get(Project, record_id)
            if project is None:
                raise NotFoundError("Проект не найден: его могли удалить")
            if not (project.impediment or "").strip():
                raise ConflictError("«Что мешает» уже сняли — подтверждать нечего")
            text = project.impediment or ""
        elif action is RoundAction.IMPEDIMENT_CLEAR:
            text = ""
        await projects.set_impediment(
            session, project_id=record_id, text=text, version=version, now=now
        )
    elif action is RoundAction.HOLD:
        await projects.set_status(
            session,
            project_id=record_id,
            status=ProjectStatus.ON_HOLD,
            reason=text,
            version=version,
        )
    elif action is RoundAction.PROJECT_DONE:
        await projects.set_status(
            session, project_id=record_id, status=ProjectStatus.DONE, reason=None, version=version
        )
    else:
        try:
            person_id = uuid.UUID(text)
        except ValueError as error:
            raise RuleViolationError("Выберите ответственного из списка") from error
        await tasks.assign(session, task_id=record_id, person_id=person_id, version=version)

    session.add(RoundMark())
    await session.flush()


# --------------------------------------------------------------------------------------
# Справочники и шаблоны вех
# --------------------------------------------------------------------------------------


def _kind(kind: str) -> DictionaryKind:
    try:
        return DictionaryKind(kind)
    except ValueError as error:
        raise NotFoundError("Такого справочника нет") from error


async def _entry(session: AsyncSession, kind: DictionaryKind, entry_id: uuid.UUID) -> Any:
    model: Any = (
        Organization if kind is DictionaryKind.ORGANIZATIONS else read_model.ENTRY_MODELS[kind]
    )
    found = await session.get(model, entry_id)
    if found is None:
        raise NotFoundError("Значения уже нет: его могли убрать")
    return found


async def rename(
    session: AsyncSession,
    *,
    kind: str,
    entry_id: uuid.UUID,
    name: str,
    version: int,
    org_kind: OrganizationKind | None,
) -> None:
    """Переименовать значение; у организации — и вид. Узбекские названия — по V22."""
    dictionary = _kind(kind)
    entry = await _entry(session, dictionary, entry_id)
    check_version(expected=version, actual=entry.version)
    if dictionary is DictionaryKind.ORGANIZATIONS:
        value = clean_name(name, limit=ORGANIZATION_NAME_MAX_LENGTH)
        if await read_model.name_taken(
            session, Organization.name, value, exclude=entry.id, id_column=Organization.id
        ):
            raise ConflictError("Организация с таким названием уже есть")
        # Краткое название в Управлении не правится (оно есть только у Центра из наполнения),
        # а карточки проектов показывают его вместо полного: не сбросить — и переименованный
        # Центр остался бы на них под прежним именем.
        if value != entry.name:
            entry.short_name = None
        entry.name = value
        if org_kind is not None:
            entry.kind = org_kind.value
    else:
        value = clean_name(name)
        model = read_model.ENTRY_MODELS[dictionary]
        if await read_model.name_taken(
            session, model.name_ru, value, exclude=entry.id, id_column=model.id
        ):
            raise ConflictError("Такое название в справочнике уже есть")
        old = entry.name_ru
        entry.name_uz_cyrl = renamed_script(old_ru=old, current=entry.name_uz_cyrl, new_ru=value)
        entry.name_uz_latn = renamed_script(old_ru=old, current=entry.name_uz_latn, new_ru=value)
        entry.name_ru = value
    await session.flush()


async def toggle(session: AsyncSession, *, kind: str, entry_id: uuid.UUID, version: int) -> None:
    """Выключить значение — оно уходит из форм, у старых записей остаётся своим; или включить."""
    dictionary = _kind(kind)
    if not dictionary.can_disable:
        raise RuleViolationError("Статус выключить нельзя: на нём правила переходов")
    entry = await _entry(session, dictionary, entry_id)
    check_version(expected=version, actual=entry.version)
    entry.is_active = not entry.is_active
    await session.flush()


async def move(
    session: AsyncSession, *, kind: str, entry_id: uuid.UUID, step: int, version: int
) -> None:
    """Выше или ниже — порядок в формах. Правка обеих переставленных записей."""
    dictionary = _kind(kind)
    if not dictionary.can_move:
        raise RuleViolationError("Организации идут по названию — их порядок не меняется")
    if step not in (-1, 1):
        raise RuleViolationError("Переставить можно на одно место вверх или вниз")
    model = read_model.ENTRY_MODELS[dictionary]
    rows: list[DictionaryEntry] = await read_model.ordered(session, model)
    index = next((i for i, row in enumerate(rows) if row.id == entry_id), None)
    if index is None:
        raise NotFoundError("Значения уже нет: его могли убрать")
    check_version(expected=version, actual=rows[index].version)
    other = index + step
    if not 0 <= other < len(rows):
        return
    if len({row.sort_order for row in rows}) < len(rows):
        # Одинаковый порядок у соседей — обменом его не поправить: сначала ровная нумерация.
        for position, row in enumerate(rows, start=1):
            row.sort_order = position * 10
    rows[index].sort_order, rows[other].sort_order = rows[other].sort_order, rows[index].sort_order
    await session.flush()


async def add(
    session: AsyncSession, *, kind: str, name: str, org_kind: OrganizationKind | None
) -> uuid.UUID:
    """Новое значение — в конец формы; узбекские названия до блока 3 повторяют русское (V22)."""
    dictionary = _kind(kind)
    if not dictionary.can_add:
        raise RuleViolationError("В этот справочник значения не добавляются")
    if dictionary is DictionaryKind.ORGANIZATIONS:
        created = await dictionaries.create_organization(
            session, name=name, kind=org_kind or OrganizationKind.MINISTRY
        )
        return created.id
    value = clean_name(name)
    model: Any = read_model.ENTRY_MODELS[dictionary]
    if await read_model.name_taken(session, model.name_ru, value, exclude=None, id_column=model.id):
        raise ConflictError("Такое название в справочнике уже есть")
    entry = model(
        # Код — технический ключ, человеку его не придумывать: название меняется, код нет.
        code=f"custom-{uuid.uuid4().hex[:12]}",
        name_ru=value,
        name_uz_cyrl=value,
        name_uz_latn=value,
        sort_order=await read_model.last_sort_order(session, model.sort_order) + 10,
        is_active=True,
    )
    session.add(entry)
    await session.flush()
    created_id: uuid.UUID = entry.id
    return created_id


async def _type(session: AsyncSession, type_id: uuid.UUID) -> ProjectTypeRef:
    found = await session.get(ProjectTypeRef, type_id)
    if found is None:
        raise NotFoundError("Такого типа проекта нет")
    return found


async def _step(
    session: AsyncSession, type_id: uuid.UUID, step_id: uuid.UUID
) -> ProjectTypeMilestone:
    step = await session.get(ProjectTypeMilestone, step_id)
    if step is None or step.project_type_id != type_id:
        raise NotFoundError("Вехи в шаблоне уже нет")
    return step


async def add_step(
    session: AsyncSession, *, type_id: uuid.UUID, name: str, offset_days: int
) -> uuid.UUID:
    """Веха в шаблон типа — встанет в новом проекте по своему сроку от начала."""
    await _type(session, type_id)
    value = clean_name(name)
    step = ProjectTypeMilestone(
        project_type_id=type_id,
        name_ru=value,
        name_uz_cyrl=value,
        name_uz_latn=value,
        offset_days=clean_offset(offset_days),
        # Номер шага — только ради уникальности места: порядок в проекте — по сроку.
        sort_order=await read_model.last_sort_order(
            session,
            ProjectTypeMilestone.sort_order,
            ProjectTypeMilestone.project_type_id == type_id,
        )
        + 10,
    )
    session.add(step)
    await session.flush()
    return step.id


async def edit_step(
    session: AsyncSession,
    *,
    type_id: uuid.UUID,
    step_id: uuid.UUID,
    name: str,
    offset_days: int,
    version: int,
) -> None:
    step = await _step(session, type_id, step_id)
    check_version(expected=version, actual=step.version)
    value = clean_name(name)
    old = step.name_ru
    step.name_uz_cyrl = renamed_script(old_ru=old, current=step.name_uz_cyrl, new_ru=value)
    step.name_uz_latn = renamed_script(old_ru=old, current=step.name_uz_latn, new_ru=value)
    step.name_ru = value
    step.offset_days = clean_offset(offset_days)
    await session.flush()


async def remove_step(
    session: AsyncSession, *, type_id: uuid.UUID, step_id: uuid.UUID, version: int
) -> None:
    """Убрать веху из шаблона. Проекты, уже заведённые по нему, свои вехи не теряют."""
    step = await _step(session, type_id, step_id)
    check_version(expected=version, actual=step.version)
    await session.delete(step)
    await session.flush()
