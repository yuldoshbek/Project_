"""Пульт — сборка экрана «что требует моего внимания сейчас» (ТЗ 1, блок 1).

Числа — лестница, «кто держит», переносы — приходят из `app.services.metrics` и больше
ниоткуда (инвариант 2). Здесь к ним добавляется то, что делает строку понятной: имя
ответственного, к чему относится строка, вопрос и последнее решение, изменения с
прошлого визита. Форма ответа — договор экрана `frontend/src/sections/pult/model.ts`:
экран строился раньше API на вымышленных данных той же формы (цикл блока, CLAUDE.md).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import LADDER, Attention
from app.domain.clock import local_date
from app.domain.pult import DECISIONS, MILESTONES, PROJECTS, TASKS, ChangeKind, classify
from app.repos import pult as read_model
from app.repos.models import User
from app.services import metrics

CHANGES_LIMIT = 20
"""Сколько изменений показать «с прошлого визита». Больше двадцати — это уже не «что
изменилось», а журнал, и для него есть раздел."""

# Имя таблицы журнала → раздел экрана.
SECTION_OF = {
    PROJECTS: "projects",
    TASKS: "tasks",
    MILESTONES: "milestones",
    DECISIONS: "decisions",
}

STEPS = tuple(step for step in LADDER if not step.is_normal)


@dataclass(frozen=True, slots=True)
class PersonRef:
    id: uuid.UUID
    name: str


@dataclass(frozen=True, slots=True)
class QuestionRef:
    id: uuid.UUID
    text: str
    asked_on: date


@dataclass(frozen=True, slots=True)
class DecisionRef:
    kind: str
    decided_on: date


@dataclass(frozen=True, slots=True)
class RowView:
    section: str
    entity_id: uuid.UUID
    title: str | None
    decision_kind: str | None
    context: str | None
    step: Attention
    deviation: int
    due_on: date | None
    original_due_on: date | None
    responsible: PersonRef | None
    question: QuestionRef | None
    last_decision: DecisionRef | None
    target_type: str
    target_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class HolderView:
    person: PersonRef
    counts: dict[str, int]
    total: int
    worst: Attention


@dataclass(frozen=True, slots=True)
class ChangeView:
    kind: ChangeKind
    section: str
    entity_id: uuid.UUID
    title: str | None
    at: datetime
    moved: tuple[date, date] | None


@dataclass(frozen=True, slots=True)
class MovedView:
    section: str
    entity_id: uuid.UUID
    title: str | None
    original_due_on: date
    due_on: date | None
    moves: int


@dataclass(frozen=True, slots=True)
class MovesView:
    period_days: int
    moves: int
    total_shift_days: int
    items: list[MovedView]


@dataclass(frozen=True, slots=True)
class PultView:
    as_of: datetime
    last_visit_at: datetime | None
    rows: list[RowView]
    counts: dict[str, int]
    on_track: int
    holders: list[HolderView]
    changes: list[ChangeView]
    deadline_moves: MovesView
    is_demo: bool


async def load(
    session: AsyncSession, *, viewer: User, now: datetime, zone: ZoneInfo, is_demo: bool
) -> PultView:
    today = local_date(now, zone)
    ladder = await metrics.ladder(session, today=today, zone=zone)

    details = await read_model.row_details(session, ladder.rows, zone)
    targets = [detail.target for detail in details.values()]
    questions = await read_model.open_questions(session, targets)
    decisions = await read_model.last_decisions(session, targets)
    holders = metrics.holders(ladder)
    moves = await metrics.deadline_moves(session, now=now, zone=zone)
    changes = await _changes(session, viewer=viewer, zone=zone)

    names = await read_model.people_names(
        session,
        [row.responsible_person_id for row in ladder.rows if row.responsible_person_id]
        + [holder.person_id for holder in holders],
    )

    def person(person_id: uuid.UUID | None) -> PersonRef | None:
        if person_id is None or person_id not in names:
            return None
        return PersonRef(id=person_id, name=names[person_id])

    rows: list[RowView] = []
    for row in ladder.rows:
        detail = details.get((row.section, row.entity_id))
        target = detail.target if detail else (row.section, row.entity_id)
        question = questions.get(target) if row.attention is Attention.AWAITING_DECISION else None
        # У строки-решения «последнее решение» — она сама: показывать его второй раз незачем.
        decision = decisions.get(target) if row.section != "decisions" else None
        rows.append(
            RowView(
                section=row.section,
                entity_id=row.entity_id,
                title=row.title,
                decision_kind=row.kind,
                context=detail.context if detail else None,
                step=row.attention,
                deviation=row.deviation,
                due_on=row.due_on,
                original_due_on=detail.original_due_on if detail else None,
                responsible=person(row.responsible_person_id),
                question=(
                    QuestionRef(
                        id=question.id,
                        text=question.text,
                        asked_on=local_date(question.created_at, zone),
                    )
                    if question
                    else None
                ),
                last_decision=(
                    DecisionRef(
                        kind=decision.kind, decided_on=local_date(decision.created_at, zone)
                    )
                    if decision
                    else None
                ),
                target_type=target[0],
                target_id=target[1],
            )
        )

    moved_keys = [(item.entity_type, item.entity_id) for item in moves.items]
    moved_titles = await read_model.titles(session, moved_keys)
    moved_dues = await read_model.due_dates(session, moved_keys, zone)

    return PultView(
        as_of=now,
        last_visit_at=viewer.last_visit_at,
        rows=rows,
        counts={step.value: ladder.count(step) for step in STEPS},
        on_track=ladder.on_track,
        holders=[
            HolderView(
                person=PersonRef(id=holder.person_id, name=names.get(holder.person_id, "")),
                counts={step.value: holder.counts[step] for step in STEPS},
                total=holder.total,
                worst=holder.worst,
            )
            for holder in holders
        ],
        changes=changes,
        deadline_moves=MovesView(
            period_days=moves.period_days,
            moves=moves.moves,
            total_shift_days=moves.total_shift_days,
            items=[
                MovedView(
                    section=SECTION_OF[item.entity_type],
                    entity_id=item.entity_id,
                    title=moved_titles.get((item.entity_type, item.entity_id)),
                    original_due_on=moved_dues[(item.entity_type, item.entity_id)][0],
                    due_on=moved_dues[(item.entity_type, item.entity_id)][1],
                    moves=item.moves,
                )
                for item in moves.items
                # Запись, которую удалили после переноса, в «держим ли сроки» не
                # показывается: переутверждать там уже нечего.
                if (item.entity_type, item.entity_id) in moved_dues
            ],
        ),
        is_demo=is_demo,
    )


async def _changes(session: AsyncSession, *, viewer: User, zone: ZoneInfo) -> list[ChangeView]:
    """Что изменилось с прошлого визита смотрящего — чужими руками.

    Свои действия сюда не попадают: руководителю незачем читать, что он сам утвердил пять
    минут назад. Первый визит — пустой список: сравнивать не с чем, и экран так и говорит.
    """
    if viewer.last_visit_at is None:
        return []
    entries = await read_model.audit_entries(
        session,
        since=viewer.last_visit_at,
        entity_types=(PROJECTS, TASKS, MILESTONES, DECISIONS),
        exclude_actor=viewer.id,
        limit=CHANGES_LIMIT * 5,
    )
    found = [change for entry in entries for change in classify(entry, zone)][:CHANGES_LIMIT]
    names = await read_model.titles(session, {(c.entity_type, c.entity_id) for c in found})
    return [
        ChangeView(
            kind=change.kind,
            section=SECTION_OF[change.entity_type],
            entity_id=change.entity_id,
            title=names.get((change.entity_type, change.entity_id)),
            at=change.at,
            moved=change.moved,
        )
        for change in found
    ]
