"""Захват — недавние записи и запись одной кнопкой (ТЗ 6, 7, блок 1).

Форма — договор экрана `frontend/src/sections/capture/model.ts`, утверждённого заказчиком
28.09.2026 на вымышленных данных той же формы (CLAUDE.md, цикл блока «экран → API»).

Куда уходит запись — допущение V17 (`docs/OPEN-QUESTIONS.md`): задача и просьба
руководителя — в «Задачи», идея, письмо и мероприятие — во входящие до своих разделов.
**Задачу заводит `tasks.create`** — тот же путь, что у строки «Новая задача», с теми же
проверками типа, ответственного, проекта и срока: у задачи один вход в базу. Запись и
задача — в одной транзакции (инвариант 5): запись без задачи или задача без пометки
«просьба руководителя» не остаются.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.capture import CaptureKind, check_author, check_fields, clean_text
from app.domain.clock import local_date
from app.domain.people import Role
from app.domain.projects import validate_horizon
from app.domain.tasks import validate_title
from app.repos import captures as read_model
from app.repos.captures import CaptureRow
from app.repos.models import Capture, User
from app.services import ideas, tasks

RECENT_LIMIT = 6
"""Сколько записей показать: больше — это уже раздел, а не ответ на «а оно сохранилось?»."""


@dataclass(frozen=True, slots=True)
class CaptureView:
    id: uuid.UUID
    kind: CaptureKind
    text: str
    due_on: date | None
    author: Role
    created_at: datetime
    destination: str
    task_code: str | None


@dataclass(frozen=True, slots=True)
class RecentView:
    as_of: datetime
    recent: list[CaptureView]
    is_demo: bool


@dataclass(frozen=True, slots=True)
class NewCapture:
    kind: CaptureKind
    text: str
    due_on: date | None
    assignee_id: uuid.UUID | None
    type_code: str | None
    project_id: uuid.UUID | None


def _view(row: CaptureRow, zone: ZoneInfo) -> CaptureView:
    """Запись, ушедшая в «Задачи», показывает название и срок самой задачи.

    Задачу потом переименовывают и переносят в «Задачах», и копия из момента записи
    разошлась бы с ними: одно дело с двумя сроками на двух экранах (инвариант 2). Сказанное
    при записи остаётся в строке записи и в журнале.
    """
    kind = CaptureKind(row.kind)
    text, due_on = row.text, row.due_on
    if row.task_id is not None and row.task_title is not None:
        text = row.task_title
        due_on = local_date(row.task_due_at, zone) if row.task_due_at else None
    return CaptureView(
        id=row.id,
        kind=kind,
        text=text,
        due_on=due_on,
        author=Role(row.author_role),
        created_at=row.created_at,
        destination="tasks" if kind.becomes_task else "inbox",
        task_code=row.task_code,
    )


async def load(
    session: AsyncSession, *, now: datetime, zone: ZoneInfo, is_demo: bool
) -> RecentView:
    """Последние записи обоих: пользователи видят всё, роль подписывает запись (инвариант 13)."""
    rows = await read_model.recent(session, limit=RECENT_LIMIT)
    return RecentView(as_of=now, recent=[_view(row, zone) for row in rows], is_demo=is_demo)


async def save(
    session: AsyncSession, *, user: User, data: NewCapture, now: datetime, zone: ZoneInfo
) -> CaptureView:
    """Запись одной кнопкой. Задача и просьба — сразу задачей, остальное — во входящие."""
    kind = data.kind
    check_author(kind, Role(user.role))
    given = {
        "due_on": data.due_on,
        "assignee_id": data.assignee_id,
        "type_code": data.type_code,
        "project_id": data.project_id,
    }
    check_fields(kind, [name for name, value in given.items() if value is not None])

    task_id: uuid.UUID | None = None
    if kind.becomes_task:
        text = validate_title(data.text)
        task_id = await tasks.create(
            session,
            user=user,
            data=tasks.NewTask(
                title=text,
                type_code=data.type_code,
                due_on=data.due_on,
                assignee_id=data.assignee_id,
                project_id=data.project_id,
            ),
            now=now,
            zone=zone,
        )
    else:
        text = clean_text(data.text)
        if data.due_on is not None:
            validate_horizon(data.due_on)

    capture = Capture(
        kind=kind.value, text=text, due_on=data.due_on, author_id=user.id, task_id=task_id
    )
    session.add(capture)
    if kind is CaptureKind.IDEA:
        # Идея из Захвата — сразу набросок раздела «Идеи и карты»: путь до «да» руководителя
        # начинается с записи, а не с переноса из входящих.
        await ideas.create_idea(session, user=user, text=text)
    await session.flush()
    (row,) = await read_model.recent(session, limit=1, ids=[capture.id])
    return _view(row, zone)
