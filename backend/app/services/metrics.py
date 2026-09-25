"""Сервис показателей: единственное место, где считаются сигналы.

Это инвариант 2 в виде кода. Экран, отчёт, уведомление и сценарий «что если» берут числа
только отсюда — два источника расчёта разошлись бы, и доверия не было бы ни к одному.
Проверяется тестом «Пульт равен сумме разделов»: он сверяет лестницу без фильтра с суммой
лестниц по разделам, и его нельзя пройти, если расчёт где-то повторили.

**Что этот модуль делает.** Берёт пороги из справочника, берёт записи из репозиториев и
превращает их в строки лестницы внимания — одинаковые для проекта, вехи, задачи и решения.
Правило ступени живёт в `app.domain.attention` и не знает ни про базу, ни про модели.

**Чего он не делает.** Не пишет в базу ничего. Сценарий «что если» (ТЗ 5) пользуется теми
же функциями с подменёнными сроками, и именно поэтому расчёт обязан оставаться чистым:
стоит здесь появиться одной записи, и «что если» начнёт менять план, который он только
показывает.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import Attention, Signal, attention_of, deviation_days, sort_key
from app.domain.decisions import DecisionState, DecisionTarget
from app.domain.dictionaries import OrganizationRole, ProjectStatus, SettingKey, TaskStatus
from app.repos.models import (
    LeaderDecision,
    Milestone,
    Organization,
    Project,
    ProjectOrganization,
    Task,
)
from app.services.dictionaries import get_setting

DEFAULT_BURN_DAYS = 7
DEFAULT_QUIET_DAYS = 14
DEFAULT_MIN_CLOSED_FOR_PACE = 10

PROJECT_TERMINAL = [status.value for status in ProjectStatus if status.is_terminal]
TASK_TERMINAL = [status.value for status in TaskStatus if status.is_terminal]


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Пороги сигналов, прочитанные один раз на весь расчёт.

    Иначе лестница для двухсот записей даст двести обращений к справочнику — и Пульт,
    ради которого система существует, будет открываться секундами.
    """

    burn_days: int
    quiet_days: int
    min_closed_for_pace: int


async def load_thresholds(session: AsyncSession) -> Thresholds:
    """Пороги из справочника (ТЗ 3.9). Значения по умолчанию — на случай пустой таблицы."""
    return Thresholds(
        burn_days=int(await get_setting(session, SettingKey.BURN_DAYS, DEFAULT_BURN_DAYS)),
        quiet_days=int(await get_setting(session, SettingKey.QUIET_DAYS, DEFAULT_QUIET_DAYS)),
        min_closed_for_pace=int(
            await get_setting(session, SettingKey.MIN_CLOSED_FOR_PACE, DEFAULT_MIN_CLOSED_FOR_PACE)
        ),
    )


@dataclass(frozen=True, slots=True)
class Row:
    """Строка лестницы внимания — то, что видит руководитель.

    Одинаковая для всех разделов: это и есть смысл лестницы. Строка проекта и строка
    поручения различаются значением `section` и подписью, а не устройством, — иначе Пульт
    пришлось бы собирать из шести разных списков и сортировать их вручную.
    """

    section: str
    """Раздел ТЗ, откуда строка: `projects`, `tasks`, `milestones`, `decisions`."""

    entity_id: uuid.UUID
    title: str
    attention: Attention
    deviation: int
    """Число дней рядом со ступенью: сколько просрочено, сколько осталось, сколько тишина."""

    due_on: date | None
    responsible_person_id: uuid.UUID | None

    @property
    def signal(self) -> Signal:
        return self.attention.signal

    @property
    def order(self) -> tuple[int, int, str]:
        return sort_key(self.attention, self.deviation, self.due_on)


@dataclass(frozen=True, slots=True)
class Ladder:
    """Лестница целиком: строки внимания и свёрнутая норма.

    Норма не выбрасывается, а считается: ТЗ 4 требует строку «и ещё N по плану» — без неё
    руководитель не знает, десять у него проектов или двести, и первая строка теряет
    масштаб.
    """

    rows: tuple[Row, ...]
    on_track: int

    @property
    def needs_attention(self) -> int:
        return len(self.rows)

    def of(self, attention: Attention) -> tuple[Row, ...]:
        return tuple(row for row in self.rows if row.attention is attention)

    def count(self, attention: Attention) -> int:
        if attention.is_normal:
            return self.on_track
        return len(self.of(attention))


async def ladder(
    session: AsyncSession,
    *,
    today: date,
    thresholds: Thresholds | None = None,
    sections: tuple[str, ...] | None = None,
) -> Ladder:
    """Лестница внимания по всем разделам или по названным.

    `sections` сужает выборку — этим же и проверяется инвариант 2: лестница без фильтра
    обязана совпадать с суммой лестниц по разделам, потому что считает их один и тот же
    код с одними и теми же порогами.
    """
    limits = thresholds or await load_thresholds(session)
    wanted = sections or ("projects", "milestones", "tasks", "decisions")

    rows: list[Row] = []
    normal = 0

    awaiting = await _targets_awaiting_decision(session)

    for section, collect in (
        ("projects", _project_rows),
        ("milestones", _milestone_rows),
        ("tasks", _task_rows),
        ("decisions", _decision_rows),
    ):
        if section not in wanted:
            continue
        found, on_track = await collect(session, today=today, limits=limits, awaiting=awaiting)
        rows.extend(found)
        normal += on_track

    rows.sort(key=lambda row: row.order)
    return Ladder(rows=tuple(rows), on_track=normal)


async def _targets_awaiting_decision(session: AsyncSession) -> set[tuple[str, uuid.UUID]]:
    """Объекты, по которым открыт вопрос к руководителю.

    Одним запросом на весь расчёт, а не по запросу на запись: «ждёт решения» — верхняя
    ступень лестницы, и проверять её приходится для каждой строки.

    Открытым вопрос делает решение вида «вернуть» — руководитель отправил работу назад и
    ждёт ответа. Прочие открытые решения ждут исполнителя, а не его, и стоят на своей
    ступени как обычная работа со сроком.
    """
    rows = await session.execute(
        select(LeaderDecision.target_type, LeaderDecision.target_id).where(
            LeaderDecision.state == DecisionState.OPEN.value,
            LeaderDecision.kind == "return",
        )
    )
    return {(target_type, target_id) for target_type, target_id in rows}


def _outside_lead_projects() -> Select[tuple[uuid.UUID]]:
    """Проекты, у которых головное ведомство — не агентство и не Центр.

    Это и есть «зависит от чужих» (ТЗ 4): работа стоит не у нас, и действие по ней —
    письмо, а не звонок ответственному.
    """
    return (
        select(ProjectOrganization.project_id)
        .join(Organization, Organization.id == ProjectOrganization.organization_id)
        .where(
            ProjectOrganization.role == OrganizationRole.LEAD_AGENCY.value,
            Organization.is_founded_by_agency.is_(False),
        )
    )


async def _project_rows(
    session: AsyncSession,
    *,
    today: date,
    limits: Thresholds,
    awaiting: set[tuple[str, uuid.UUID]],
) -> tuple[list[Row], int]:
    outside = set(await session.scalars(_outside_lead_projects()))
    life = await _project_life(session)

    rows: list[Row] = []
    normal = 0

    for project in await session.scalars(
        select(Project).where(Project.status_code.notin_(PROJECT_TERMINAL))
    ):
        state = attention_of(
            is_terminal=False,
            awaits_decision=(DecisionTarget.PROJECT.value, project.id) in awaiting,
            due_on=project.due_on,
            today=today,
            last_sign_of_life=life.get(project.id),
            lead_is_outside=project.id in outside,
            burn_days=limits.burn_days,
            quiet_days=limits.quiet_days,
        )
        if state is None:
            continue
        if state.is_normal:
            normal += 1
            continue
        rows.append(
            Row(
                section="projects",
                entity_id=project.id,
                title=project.title,
                attention=state,
                deviation=deviation_days(
                    state,
                    due_on=project.due_on,
                    today=today,
                    last_sign_of_life=life.get(project.id),
                ),
                due_on=project.due_on,
                responsible_person_id=project.responsible_person_id,
            )
        )

    return rows, normal


async def _project_life(session: AsyncSession) -> dict[uuid.UUID, date]:
    """Признак жизни проекта: самое свежее движение по его задачам и вехам (ТЗ 4).

    Одним запросом на все проекты. Запрос на проект превратил бы открытие Пульта в
    двести обращений к базе — и замечают это не сразу, а когда проектов станет много.
    """
    found: dict[uuid.UUID, date] = {}

    by_task = await session.execute(
        select(Task.project_id, func.max(Task.updated_at))
        .where(Task.project_id.is_not(None))
        .group_by(Task.project_id)
    )
    by_milestone = await session.execute(
        select(Milestone.project_id, func.max(Milestone.updated_at)).group_by(Milestone.project_id)
    )

    for project_id, moment in list(by_task) + list(by_milestone):
        if project_id is None or moment is None:
            continue
        seen = moment.date()
        if project_id not in found or found[project_id] < seen:
            found[project_id] = seen

    return found


async def _milestone_rows(
    session: AsyncSession,
    *,
    today: date,
    limits: Thresholds,
    awaiting: set[tuple[str, uuid.UUID]],
) -> tuple[list[Row], int]:
    rows: list[Row] = []
    normal = 0

    statement = (
        select(Milestone)
        .join(Project, Project.id == Milestone.project_id)
        .where(
            Milestone.is_passed.is_(False),
            Project.status_code.notin_(PROJECT_TERMINAL),
        )
    )

    for milestone in await session.scalars(statement):
        state = attention_of(
            is_terminal=False,
            awaits_decision=(DecisionTarget.MILESTONE.value, milestone.id) in awaiting,
            due_on=milestone.due_on,
            today=today,
            # У вехи собственного движения нет: её либо проходят, либо нет. Молчание по
            # ней — это молчание проекта, и считать его дважды значило бы показать одну
            # тишину двумя строками.
            last_sign_of_life=today,
            lead_is_outside=False,
            burn_days=limits.burn_days,
            quiet_days=limits.quiet_days,
        )
        if state is None:
            continue
        if state.is_normal:
            normal += 1
            continue
        rows.append(
            Row(
                section="milestones",
                entity_id=milestone.id,
                title=milestone.title,
                attention=state,
                deviation=deviation_days(
                    state, due_on=milestone.due_on, today=today, last_sign_of_life=None
                ),
                due_on=milestone.due_on,
                responsible_person_id=None,
            )
        )

    return rows, normal


async def _task_rows(
    session: AsyncSession,
    *,
    today: date,
    limits: Thresholds,
    awaiting: set[tuple[str, uuid.UUID]],
) -> tuple[list[Row], int]:
    rows: list[Row] = []
    normal = 0

    for task in await session.scalars(select(Task).where(Task.status.notin_(TASK_TERMINAL))):
        # Срок задачи — момент, а не дата: сравнение с «сегодня» идёт по календарным дням
        # Ташкента (инвариант 8), иначе задача становится просроченной в пять утра.
        due_on = task.due_at.date() if task.due_at else None
        life = task.updated_at.date() if task.updated_at else task.created_at.date()

        state = attention_of(
            is_terminal=False,
            awaits_decision=(DecisionTarget.TASK.value, task.id) in awaiting,
            due_on=due_on,
            today=today,
            last_sign_of_life=life,
            lead_is_outside=False,
            burn_days=limits.burn_days,
            quiet_days=limits.quiet_days,
        )
        if state is None:
            continue
        if state.is_normal:
            normal += 1
            continue
        rows.append(
            Row(
                section="tasks",
                entity_id=task.id,
                title=task.title,
                attention=state,
                deviation=deviation_days(state, due_on=due_on, today=today, last_sign_of_life=life),
                due_on=due_on,
                responsible_person_id=task.assignee_person_id,
            )
        )

    return rows, normal


async def _decision_rows(
    session: AsyncSession,
    *,
    today: date,
    limits: Thresholds,
    awaiting: set[tuple[str, uuid.UUID]],
) -> tuple[list[Row], int]:
    """Решения руководителя, которые он принял, а исполнения нет.

    Они стоят в лестнице наравне с работой: решение, о котором забыли, — это ровно то,
    из-за чего система и заводилась. На ступень «ждёт решения» они не попадают никогда:
    решение уже принято, ждут его исполнения.
    """
    rows: list[Row] = []
    normal = 0

    for decision in await session.scalars(
        select(LeaderDecision).where(LeaderDecision.state == DecisionState.OPEN.value)
    ):
        life = decision.updated_at.date() if decision.updated_at else decision.created_at.date()
        state = attention_of(
            is_terminal=False,
            awaits_decision=False,
            due_on=decision.due_on,
            today=today,
            last_sign_of_life=life,
            lead_is_outside=False,
            burn_days=limits.burn_days,
            quiet_days=limits.quiet_days,
        )
        if state is None:
            continue
        if state.is_normal:
            normal += 1
            continue
        rows.append(
            Row(
                section="decisions",
                entity_id=decision.id,
                title=decision.text or decision.kind,
                attention=state,
                deviation=deviation_days(
                    state, due_on=decision.due_on, today=today, last_sign_of_life=life
                ),
                due_on=decision.due_on,
                responsible_person_id=decision.assignee_person_id,
            )
        )

    return rows, normal
