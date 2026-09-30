"""Календарь — правила раздела (ТЗ 2, 5, 11).

Календарь собирает даты всех разделов (CONTEXT: «все сроки, вехи, мероприятия и доклады из
всех разделов плюс годовые циклы»). Здесь — чистые правила, из которых сервис показателей
собирает ответ «где неделя перегружена?»: какие даты считаются одним сроком и какой день
горячий.

Два правила ТЗ не называет, и они записаны допущениями (docs/OPEN-QUESTIONS.md): что такое
горячий день — V15, есть ли у даты годового цикла ступень — V16 (нет).
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

MAX_RANGE_DAYS = 450
"""Сколько дней отдаёт один запрос. Сетка месяца — до 42 дней; список телефона дорастает
до горизонта циклов, это год. Больше — уже не календарь, а выгрузка."""


class CalendarKind(StrEnum):
    """Откуда дата. Порядок объявления — порядок показа внутри дня и в подписи горячего дня."""

    MILESTONE = "milestone"
    PROJECT = "project"
    TASK = "task"
    DECISION = "decision"
    CYCLE = "cycle"

    @property
    def order(self) -> int:
        return list(CalendarKind).index(self)


@dataclass(frozen=True, slots=True)
class ProjectEnd:
    """Срок проекта в календаре: чей и в какой день."""

    project_id: uuid.UUID
    due_on: date
    is_done: bool


@dataclass(frozen=True, slots=True)
class Mark:
    """Веха в календаре: её проект и день."""

    milestone_id: uuid.UUID
    project_id: uuid.UUID
    due_on: date
    is_done: bool


def ends_with_milestone(
    ends: Iterable[ProjectEnd], marks: Sequence[Mark]
) -> dict[uuid.UUID, uuid.UUID]:
    """Сроки проектов, которые совпали с вехой того же проекта: проект → веха.

    Итоговая веха обычно и стоит в день срока проекта, и это одно дело: двумя строками оно
    считалось бы дважды, и любой конец проекта плюс одна чужая задача делал бы день
    «тесным» (V15). Такой срок показывается строкой вехи — «и срок проекта». Сливаются
    только записи в одном состоянии: закрытый проект с открытой вехой — два разных факта.
    Если вех в этот день несколько, срок идёт к первой по порядку, который задал вызов.
    """
    by_day: dict[tuple[uuid.UUID, date, bool], uuid.UUID] = {}
    for mark in marks:
        by_day.setdefault((mark.project_id, mark.due_on, mark.is_done), mark.milestone_id)
    merged: dict[uuid.UUID, uuid.UUID] = {}
    for end in ends:
        found = by_day.get((end.project_id, end.due_on, end.is_done))
        if found is not None:
            merged[end.project_id] = found
    return merged


@dataclass(frozen=True, slots=True)
class HotDay:
    """Горячий день: сколько незакрытых сроков сходится и каких (ТЗ 5)."""

    date: date
    count: int
    kinds: dict[CalendarKind, int]


def hot_days(
    open_dates: Iterable[tuple[date, CalendarKind]],
    *,
    since: date,
    until: date,
    threshold: int,
) -> list[HotDay]:
    """Горячие дни с `since` по `until`: незакрытых сроков в день не меньше порога (V15).

    `open_dates` — только незакрытое и уже с одним сроком на одно дело
    (`ends_with_milestone`). Прошедшие дни горячими не бывают — это решает вызов, задавая
    `since` не раньше сегодняшнего: несделанное там уже «срок прошёл».
    """
    per_day: dict[date, Counter[CalendarKind]] = {}
    for day, kind in open_dates:
        if since <= day <= until:
            per_day.setdefault(day, Counter())[kind] += 1
    hot: list[HotDay] = []
    for day in sorted(per_day):
        counted = per_day[day]
        total = sum(counted.values())
        if total >= threshold:
            kinds = {kind: counted[kind] for kind in sorted(counted, key=lambda each: each.order)}
            hot.append(HotDay(date=day, count=total, kinds=kinds))
    return hot


def window(today: date, days: int) -> tuple[date, date]:
    """Окно ответа «где неделя перегружена?»: с сегодняшнего на `days` дней вперёд."""
    return today, today + timedelta(days=days - 1)
