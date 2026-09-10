"""Проекты: сценарии использования.

Транзакция живёт здесь, здесь же проверяются правила домена. Роутер не решает ничего:
он разбирает запрос и собирает ответ (CLAUDE.md, границы слоёв).

Запись в журнал изменений не вызывается отсюда ни разу — её делают обработчики сессии
([ADR-0010](../../../docs/adr/ADR-0010-audit-log.md), ORB-009). Появление здесь строки
`AuditLog(...)` означало бы, что рядом заведут место, где её забыли.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dictionaries import Health, ProjectStatus, SettingKey
from app.domain.errors import NotFoundError
from app.domain.projects import (
    DEFAULT_IMPEDIMENT_STALE_DAYS,
    Classification,
    ProgressMode,
    ProjectKind,
    has_active_impediment,
    impediment_is_stale,
    validate_dates,
    validate_progress,
    validate_status_reason,
)
from app.domain.projects import health as compute_health
from app.repos.models import Organization, PriorityRef, Project, ProjectPartner
from app.services import codes
from app.services.dictionaries import get_setting

DEFAULT_WARN_DAYS = 3
DEFAULT_WARN_RATIO = 0.8

CODE_PREFIX = "PRJ"
CODE_DIGITS = 3

_UNSET: Any = object()
"""Отличает «поле не прислали» от «поле обнулили».

Без этого `None` в частичном изменении означал бы и то и другое, и стереть причину
приостановки было бы невозможно — либо, наоборот, любое изменение стирало бы её молча.
"""


@dataclass(frozen=True, slots=True)
class ProjectRules:
    """Пороги из справочника, прочитанные один раз на весь список.

    Иначе расчёт для двухсот проектов даст двести обращений к справочнику — и экран,
    ради которого система существует, будет открываться секундами (ТЗ 10.2).
    """

    warn_days: int
    warn_ratio: float
    warn_days_by_priority: dict[str, int]
    impediment_stale_days: int

    def of(self, project: Project, *, today: date) -> Health:
        return compute_health(
            status=ProjectStatus(project.status_code),
            started_on=project.started_on,
            due_on=project.due_on,
            today=today,
            warn_days=self.warn_days_by_priority.get(project.priority_code, self.warn_days),
            warn_ratio=self.warn_ratio,
        )

    def impediment_is_stale(self, project: Project, *, now: datetime) -> bool:
        return impediment_is_stale(
            updated_at=project.impediment_updated_at,
            now=now,
            stale_days=self.impediment_stale_days,
        )

    def has_active_impediment(self, project: Project, *, now: datetime) -> bool:
        return has_active_impediment(
            impediment=project.impediment,
            updated_at=project.impediment_updated_at,
            now=now,
            stale_days=self.impediment_stale_days,
        )


async def load_project_rules(session: AsyncSession) -> ProjectRules:
    """Пороги из справочника настроек и переопределения по приоритету (ТЗ 6.8)."""
    warn_days = await get_setting(session, SettingKey.WARN_DAYS, DEFAULT_WARN_DAYS)
    warn_ratio = await get_setting(session, SettingKey.WARN_RATIO, DEFAULT_WARN_RATIO)
    stale_days = await get_setting(
        session, SettingKey.IMPEDIMENT_STALE_DAYS, DEFAULT_IMPEDIMENT_STALE_DAYS
    )

    overrides = await session.execute(
        select(PriorityRef.code, PriorityRef.warn_days_override).where(
            PriorityRef.warn_days_override.is_not(None)
        )
    )
    return ProjectRules(
        warn_days=int(warn_days),
        warn_ratio=float(warn_ratio),
        warn_days_by_priority={code: int(days) for code, days in overrides},
        impediment_stale_days=int(stale_days),
    )


@dataclass(slots=True)
class ProjectDraft:
    """Что приходит при создании."""

    title: str
    direction_id: uuid.UUID
    status_code: str
    priority_code: str
    started_on: date
    due_on: date
    kind: ProjectKind = ProjectKind.PROJECT
    classification: Classification = Classification.INTERNAL
    description: str | None = None
    curator_person_id: uuid.UUID | None = None
    status_reason: str | None = None
    finished_on: date | None = None
    progress_pct: int = 0
    progress_mode: ProgressMode = ProgressMode.AUTO
    budget_note: str | None = None


@dataclass(slots=True)
class ProjectPatch:
    """Что приходит при изменении. `_UNSET` — «поле не прислали»."""

    title: Any = _UNSET
    description: Any = _UNSET
    kind: Any = _UNSET
    classification: Any = _UNSET
    direction_id: Any = _UNSET
    curator_person_id: Any = _UNSET
    status_code: Any = _UNSET
    status_reason: Any = _UNSET
    priority_code: Any = _UNSET
    started_on: Any = _UNSET
    due_on: Any = _UNSET
    finished_on: Any = _UNSET
    progress_pct: Any = _UNSET
    progress_mode: Any = _UNSET
    budget_note: Any = _UNSET

    def assigned(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in self.__slots__
            if getattr(self, name) is not _UNSET
        }


async def next_code(session: AsyncSession, *, today: date) -> str:
    """Следующий человекочитаемый номер проекта: PRJ-2026-001."""
    return await codes.next_code(
        session, column=Project.code, prefix=CODE_PREFIX, digits=CODE_DIGITS, today=today
    )


async def create(
    session: AsyncSession,
    draft: ProjectDraft,
    *,
    created_by: uuid.UUID | None,
    today: date,
) -> Project:
    validate_dates(started_on=draft.started_on, due_on=draft.due_on)
    validate_status_reason(status=ProjectStatus(draft.status_code), reason=draft.status_reason)
    validate_progress(draft.progress_pct)

    project = Project(
        code=await next_code(session, today=today),
        title=draft.title.strip(),
        description=draft.description,
        kind=draft.kind.value,
        classification=draft.classification.value,
        direction_id=draft.direction_id,
        curator_person_id=draft.curator_person_id,
        status_code=draft.status_code,
        status_reason=draft.status_reason,
        priority_code=draft.priority_code,
        started_on=draft.started_on,
        due_on=draft.due_on,
        finished_on=draft.finished_on,
        progress_pct=draft.progress_pct,
        progress_mode=draft.progress_mode.value,
        budget_note=draft.budget_note,
        created_by=created_by,
    )
    session.add(project)
    await session.flush()
    return project


async def get(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        # Не «нет доступа»: сообщение о запрете подтверждает, что запись существует, и
        # по перебору идентификаторов узнаётся состав портфеля (ADR-0007).
        raise NotFoundError("Проект не найден")
    return project


async def update(session: AsyncSession, project_id: uuid.UUID, patch: ProjectPatch) -> Project:
    project = await get(session, project_id)
    changes = patch.assigned()

    for name, value in changes.items():
        setattr(project, name, value.value if isinstance(value, Enum) else value)

    validate_dates(started_on=project.started_on, due_on=project.due_on)
    validate_status_reason(status=ProjectStatus(project.status_code), reason=project.status_reason)
    validate_progress(project.progress_pct)

    await session.flush()
    return project


async def set_impediment(
    session: AsyncSession,
    project_id: uuid.UUID,
    text: str | None,
    *,
    now: datetime | None = None,
) -> Project:
    """Записывает строку «что мешает» и отмечает момент.

    Дата обновляется при **каждом** обращении к этому эндпоинту, даже если текст не
    изменился: обращение сюда — это подтверждение, что помеха всё ещё та же и всё ещё
    есть. Именно на этот вопрос дата и отвечает.

    Очистка строки очищает и дату: дата без текста ничего не датирует.
    """
    project = await get(session, project_id)
    cleaned = (text or "").strip() or None

    project.impediment = cleaned
    project.impediment_updated_at = (now or datetime.now(UTC)) if cleaned else None
    await session.flush()
    return project


async def delete(session: AsyncSession, project_id: uuid.UUID) -> None:
    project = await get(session, project_id)
    await session.delete(project)
    await session.flush()


@dataclass(slots=True)
class ProjectFilter:
    """Чем сужается список."""

    direction_id: uuid.UUID | None = None
    status_code: str | None = None
    priority_code: str | None = None
    kind: ProjectKind | None = None
    classification: Classification | None = None
    curator_person_id: uuid.UUID | None = None
    search: str | None = None
    health: Health | None = None
    organization_id: uuid.UUID | None = None
    partner_search: str | None = None


SORTABLE = {
    "code": Project.code,
    "title": Project.title,
    "due_on": Project.due_on,
    "started_on": Project.started_on,
    "progress_pct": Project.progress_pct,
    "created_at": Project.created_at,
}


def _apply(statement: Select[Any], filters: ProjectFilter) -> Select[Any]:
    if filters.direction_id is not None:
        statement = statement.where(Project.direction_id == filters.direction_id)
    if filters.status_code is not None:
        statement = statement.where(Project.status_code == filters.status_code)
    if filters.priority_code is not None:
        statement = statement.where(Project.priority_code == filters.priority_code)
    if filters.kind is not None:
        statement = statement.where(Project.kind == filters.kind.value)
    if filters.classification is not None:
        statement = statement.where(Project.classification == filters.classification.value)
    if filters.curator_person_id is not None:
        statement = statement.where(Project.curator_person_id == filters.curator_person_id)
    if filters.organization_id is not None:
        statement = statement.where(
            Project.id.in_(
                select(ProjectPartner.project_id).where(
                    ProjectPartner.organization_id == filters.organization_id
                )
            )
        )
    if filters.partner_search:
        # «Что у нас с ЕКА» — вопрос сценария U6. Полноценный поиск на трёх письменностях
        # даёт ORB-033; здесь совпадение по подстроке названия и краткого имени.
        pattern = f"%{filters.partner_search.strip()}%"
        statement = statement.where(
            Project.id.in_(
                select(ProjectPartner.project_id)
                .join(Organization, ProjectPartner.organization_id == Organization.id)
                .where(Organization.name.ilike(pattern) | Organization.short_name.ilike(pattern))
            )
        )
    if filters.search:
        # Совпадение по подстроке. Поиск на трёх письменностях — ORB-033: он требует
        # своего индекса и нормализации, и делать его наполовину здесь значит получить
        # два разных поиска в одной системе.
        statement = statement.where(Project.title.ilike(f"%{filters.search.strip()}%"))
    return statement


async def list_projects(
    session: AsyncSession,
    filters: ProjectFilter | None = None,
    *,
    today: date,
    sort_by: str = "due_on",
    descending: bool = False,
) -> list[tuple[Project, Health]]:
    """Проекты вместе с их цветом.

    Цвет считается здесь, а не отдаётся отдельным запросом: список без светофора
    бесполезен, а два обращения ради одного экрана — лишнее ожидание.

    Фильтр по цвету применяется после выборки, а не в SQL: цвет не хранится (ADR-0005),
    и условие на него в запросе означало бы повторение правила на языке базы — второе
    место, где живёт то же правило.
    """
    filters = filters or ProjectFilter()
    column = SORTABLE.get(sort_by, Project.due_on)

    statement = _apply(select(Project), filters)
    statement = statement.order_by(column.desc() if descending else column.asc())

    rules = await load_project_rules(session)
    rows = [
        (project, rules.of(project, today=today)) for project in await session.scalars(statement)
    ]
    if filters.health is not None:
        rows = [row for row in rows if row[1] is filters.health]
    return rows
