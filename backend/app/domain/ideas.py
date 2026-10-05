"""Идеи и карты — правила раздела (ТЗ 3.6, 5).

**Идея** — быстрая запись замысла. Путь: набросок → на рассмотрении у руководителя →
решено; решение — проект, задача или «отложено» (CONTEXT). Решает руководитель: это его
«да» (ТЗ 5, «Что ждёт моего „да“?»), и решение «в проект» или «в задачу» сразу заводит
настоящую запись — одним действием (критерий 1 блока 3).

**Карта** — общая интеллект-карта: узлы и связи «родитель — потомок». В режиме
«Набросок» узлы свободные; в режиме «Структура» узлы и есть проекты и задачи, и узел без
связи с настоящей записью виден как несвязанный.

Допущения (docs/OPEN-QUESTIONS.md): V46 — возраст идеи на рассмотрении считается от
отправки на рассмотрение, а не от записи: набросок может лежать сколько угодно, ждать
руководителя начинает только отправленное; V47 — «отложено» не тупик: отложенную идею
можно снова отправить на рассмотрение.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.domain.errors import RuleViolationError

TEXT_MAX_LENGTH = 1000
"""Идея — одна-две фразы, как запись Захвата (`app.domain.capture.TEXT_MAX_LENGTH`)."""

NODE_TEXT_MAX_LENGTH = 300
"""Узел карты — подпись, а не документ: длиннее не помещается в карточку узла."""

MAP_TITLE_MAX_LENGTH = 200

CANVAS_LIMIT = 20_000
"""Координаты узла — пиксели полотна. Дальше двадцати тысяч узел не найти прокруткой: это
ошибка перетаскивания, а не замысел."""


class IdeaStep(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    DECIDED = "decided"


class Outcome(StrEnum):
    """Решение по идее (ТЗ 3.6)."""

    PROJECT = "project"
    TASK = "task"
    POSTPONED = "postponed"


class MapMode(StrEnum):
    SKETCH = "sketch"
    STRUCTURE = "structure"


class Question(StrEnum):
    AWAITING = "awaiting"
    """«Что ждёт моего „да“?» — идеи на рассмотрении по возрасту (ТЗ 5)."""


def clean_text(text: str, *, limit: int = TEXT_MAX_LENGTH) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        raise RuleViolationError("Текст не может быть пустым")
    if len(cleaned) > limit:
        raise RuleViolationError(f"Текст длиннее {limit} знаков")
    return cleaned


def clean_title(title: str) -> str:
    return clean_text(title, limit=MAP_TITLE_MAX_LENGTH)


def check_point(x: int, y: int) -> None:
    if not (-CANVAS_LIMIT <= x <= CANVAS_LIMIT and -CANVAS_LIMIT <= y <= CANVAS_LIMIT):
        raise RuleViolationError("Узел за пределами полотна")


def check_to_review(step: IdeaStep, outcome: Outcome | None) -> None:
    """На рассмотрение — набросок или отложенная идея (V47); решённую в проект — нет."""
    if step is IdeaStep.REVIEW:
        raise RuleViolationError("Идея уже на рассмотрении")
    if step is IdeaStep.DECIDED and outcome is not Outcome.POSTPONED:
        raise RuleViolationError("По идее уже решено")


def check_decision(step: IdeaStep, outcome: Outcome | None) -> None:
    """Решить можно идею, которая ещё не превратилась в проект или задачу.

    Руководитель может решить и набросок — не дожидаясь отправки: «да» руководителя не
    нуждается в разрешении помощника. Отложенную — тоже: «отложено» не тупик (V47).
    """
    if step is IdeaStep.DECIDED and outcome is not Outcome.POSTPONED:
        raise RuleViolationError("По идее уже решено")


def check_parent(
    node_id: uuid.UUID | None,
    parent_id: uuid.UUID | None,
    parents: dict[uuid.UUID, uuid.UUID | None],
) -> None:
    """Родитель узла — узел той же карты и не его потомок: иначе связи замкнутся в кольцо.

    `parents` — все узлы карты: узел → его родитель.
    """
    if parent_id is None:
        return
    if parent_id not in parents:
        raise RuleViolationError("Родитель — узел другой карты или его нет")
    seen: set[uuid.UUID] = set()
    current: uuid.UUID | None = parent_id
    while current is not None:
        if current == node_id:
            raise RuleViolationError("Узел не может стать потомком самого себя")
        if current in seen:
            break
        seen.add(current)
        current = parents.get(current)


def subtree(root: uuid.UUID, parents: dict[uuid.UUID, uuid.UUID | None]) -> set[uuid.UUID]:
    """Узел и все его потомки — удаляются вместе: потомок без родителя потерял бы смысл."""
    children: dict[uuid.UUID, list[uuid.UUID]] = {}
    for node, parent in parents.items():
        if parent is not None:
            children.setdefault(parent, []).append(node)
    found = {root}
    stack = [root]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in found:
                found.add(child)
                stack.append(child)
    return found


@dataclass(frozen=True, slots=True)
class Waiting:
    id: uuid.UUID
    since: date


@dataclass(frozen=True, slots=True)
class Answer:
    key: Question
    count: int
    oldest_days: int
    oldest_id: uuid.UUID | None
    rows: list[uuid.UUID]


def awaiting(ideas: Iterable[Waiting], today: date) -> Answer:
    """Идеи на рассмотрении — старшие первыми: дольше всех ждёт — первым и решается (V46)."""
    ordered: Sequence[Waiting] = sorted(ideas, key=lambda each: (each.since, str(each.id)))
    oldest = ordered[0] if ordered else None
    return Answer(
        key=Question.AWAITING,
        count=len(ordered),
        oldest_days=(today - oldest.since).days if oldest else 0,
        oldest_id=oldest.id if oldest else None,
        rows=[each.id for each in ordered],
    )
