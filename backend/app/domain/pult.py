"""Пульт: что считать изменением с прошлого визита и что — переносом срока.

Оба ответа читаются из журнала изменений (ADR-0010), а не из отдельных таблиц: журнал уже
хранит «было → стало» по каждому полю, и вторая копия того же разошлась бы с ним.

Здесь только правила над записями журнала — ни базы, ни запросов. Записи достаёт
`app.repos.pult`, числа из них собирает `app.services.metrics` (инвариант 2).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.audit import AuditAction
from app.domain.clock import local_date
from app.domain.decisions import DecisionState
from app.domain.dictionaries import ProjectStatus, TaskStatus


class ChangeKind(StrEnum):
    """Что руководитель видит в «С прошлого визита» (ТЗ 5: «строка изменений»)."""

    CREATED = "created"
    CLOSED = "closed"
    DEADLINE_MOVED = "deadline_moved"
    MILESTONE_PASSED = "milestone_passed"
    DECISION_DONE = "decision_done"


# Сущности журнала — имена таблиц (`AuditLog.entity_type`).
PROJECTS = "projects"
TASKS = "tasks"
MILESTONES = "milestones"
DECISIONS = "leader_decisions"

# Поле срока у каждой сущности. У задачи срок — момент, у проекта и вехи — дата.
DUE_FIELD = {PROJECTS: "due_on", MILESTONES: "due_on", TASKS: "due_at"}

_CLOSED_STATUS = {
    PROJECTS: ("status_code", {s.value for s in ProjectStatus if s.is_terminal}),
    TASKS: ("status", {s.value for s in TaskStatus if s.is_terminal}),
}


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Запись журнала в том виде, в каком её читает правило."""

    occurred_at: datetime
    entity_type: str
    entity_id: uuid.UUID
    action: str
    changes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Change:
    kind: ChangeKind
    entity_type: str
    entity_id: uuid.UUID
    at: datetime
    moved: tuple[date, date] | None = None


def _as_date(value: Any, zone: ZoneInfo) -> date | None:
    """Дата срока из значения журнала: дата как есть, момент — по Ташкенту."""
    if not isinstance(value, str):
        return None
    if len(value) == 10:
        return date.fromisoformat(value)
    return local_date(datetime.fromisoformat(value), zone)


def _to(changes: dict[str, Any], field: str) -> Any:
    side = changes.get(field)
    return side.get("to") if isinstance(side, dict) else None


def classify(entry: AuditEntry, zone: ZoneInfo) -> list[Change]:
    """Изменения, которые одна запись журнала даёт «С прошлого визита».

    Одна правка может дать несколько: задачу закрыли и заодно сдвинули ей срок. Вехи при
    создании не показываются: их подставляет шаблон вместе с проектом, и десять строк
    «новая веха» заслонили бы одну строку «новый проект».
    """
    found: list[Change] = []

    def add(kind: ChangeKind, moved: tuple[date, date] | None = None) -> None:
        found.append(
            Change(
                kind=kind,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                at=entry.occurred_at,
                moved=moved,
            )
        )

    if entry.action == AuditAction.CREATED:
        if entry.entity_type in (PROJECTS, TASKS):
            add(ChangeKind.CREATED)
        return found

    if entry.action != AuditAction.UPDATED:
        return found

    closed = _CLOSED_STATUS.get(entry.entity_type)
    if closed and _to(entry.changes, closed[0]) in closed[1]:
        add(ChangeKind.CLOSED)

    moved = due_shift(entry, zone)
    if moved:
        add(ChangeKind.DEADLINE_MOVED, moved)

    if entry.entity_type == MILESTONES and _to(entry.changes, "is_passed") is True:
        add(ChangeKind.MILESTONE_PASSED)

    if entry.entity_type == DECISIONS and _to(entry.changes, "state") == DecisionState.DONE:
        add(ChangeKind.DECISION_DONE)

    return found


def due_shift(entry: AuditEntry, zone: ZoneInfo) -> tuple[date, date] | None:
    """«Было → стало» по сроку, если запись журнала его меняла, иначе `None`."""
    field = DUE_FIELD.get(entry.entity_type)
    side = entry.changes.get(field) if field else None
    if entry.action != AuditAction.UPDATED or not isinstance(side, dict):
        return None
    before, after = _as_date(side.get("from"), zone), _as_date(side.get("to"), zone)
    if before is None or after is None or before == after:
        return None
    return before, after


class PeriodKind(StrEnum):
    """Отчёт недели и месяца — вкладка Пульта (ТЗ 2, критерий 6 блока 1)."""

    WEEK = "week"
    MONTH = "month"


def period_bounds(kind: PeriodKind, offset: int, today: date) -> tuple[date, date]:
    """Первый и последний день отчётного периода; `offset` — сколько периодов назад.

    Календарные неделя и месяц, а не «последние семь дней»: отчёт печатают и кладут в
    папку, и «неделя с 22 по 28 сентября» у двух распечаток обязана быть одной и той же.
    Неделя — с понедельника, как рабочая неделя агентства.
    """
    if kind is PeriodKind.WEEK:
        monday = today - timedelta(days=today.weekday()) - timedelta(weeks=offset)
        return monday, monday + timedelta(days=6)

    month_index = today.year * 12 + today.month - 1 - offset
    first = date(month_index // 12, month_index % 12 + 1, 1)
    next_index = month_index + 1
    after = date(next_index // 12, next_index % 12 + 1, 1)
    return first, after - timedelta(days=1)


@dataclass(frozen=True, slots=True)
class PeriodTotals:
    """Итоги периода по журналу: что сделано, а не сколько всего накопилось.

    ТЗ 5 запрещает метрики, которые только растут («закрыто задач всего»). Здесь каждое
    число — за период, и у каждого есть ответ на вопрос «что изменилось за неделю».
    """

    created_projects: int
    created_tasks: int
    closed_tasks: int
    closed_projects: int
    passed_milestones: int
    decisions_made: int
    decisions_done: int
    moves: int
    shift_days: int


def period_totals(entries: Iterable[AuditEntry], *, zone: ZoneInfo) -> PeriodTotals:
    """Итоги по записям журнала за период — тем же правилом, что «С прошлого визита»."""
    counts: dict[tuple[ChangeKind, str], int] = {}
    decisions_made = 0
    moves = 0
    shift_days = 0
    for entry in entries:
        if entry.entity_type == DECISIONS and entry.action == AuditAction.CREATED:
            decisions_made += 1
        for change in classify(entry, zone):
            key = (change.kind, change.entity_type)
            counts[key] = counts.get(key, 0) + 1
            if change.kind is ChangeKind.DEADLINE_MOVED and change.moved:
                shift = (change.moved[1] - change.moved[0]).days
                if shift > 0:
                    moves += 1
                    shift_days += shift

    def count(kind: ChangeKind, entity_type: str) -> int:
        return counts.get((kind, entity_type), 0)

    return PeriodTotals(
        created_projects=count(ChangeKind.CREATED, PROJECTS),
        created_tasks=count(ChangeKind.CREATED, TASKS),
        closed_tasks=count(ChangeKind.CLOSED, TASKS),
        closed_projects=count(ChangeKind.CLOSED, PROJECTS),
        passed_milestones=count(ChangeKind.MILESTONE_PASSED, MILESTONES),
        decisions_made=decisions_made,
        decisions_done=count(ChangeKind.DECISION_DONE, DECISIONS),
        moves=moves,
        shift_days=shift_days,
    )


@dataclass(frozen=True, slots=True)
class MovedItem:
    entity_type: str
    entity_id: uuid.UUID
    moves: int
    shift_days: int


@dataclass(frozen=True, slots=True)
class DeadlineMoves:
    """«Держим ли мы свои сроки?» — ответ числом и список самых переносимых (ТЗ 5)."""

    period_days: int
    moves: int
    total_shift_days: int
    items: tuple[MovedItem, ...]


def deadline_moves(
    entries: Iterable[AuditEntry], *, zone: ZoneInfo, period_days: int, top: int
) -> DeadlineMoves:
    """Переносы сроков за период по журналу.

    Перенос — сдвиг срока **позже**: срок, подтянутый раньше, — не то, о чём спрашивает
    «держим ли мы свои сроки». Суммарный сдвиг — сумма дней таких переносов. Список —
    самые переносимые записи: сначала по числу переносов, при равном — по сдвигу.
    """
    per_item: dict[tuple[str, uuid.UUID], list[int]] = {}
    for entry in entries:
        shift = due_shift(entry, zone)
        if shift is None:
            continue
        days = (shift[1] - shift[0]).days
        if days > 0:
            per_item.setdefault((entry.entity_type, entry.entity_id), []).append(days)

    items = sorted(
        (
            MovedItem(entity_type=kind, entity_id=entity_id, moves=len(days), shift_days=sum(days))
            for (kind, entity_id), days in per_item.items()
        ),
        key=lambda item: (-item.moves, -item.shift_days),
    )
    return DeadlineMoves(
        period_days=period_days,
        moves=sum(item.moves for item in items),
        total_shift_days=sum(item.shift_days for item in items),
        items=tuple(items[:top]),
    )
