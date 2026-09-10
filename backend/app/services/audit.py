"""Запись в журнал изменений.

**Журнал пишется сам.** Точечных вызовов вида `write_audit(...)` из роутеров нет и не
должно быть — их забывают, и запись годами меняется бесследно
([ADR-0010](../../../docs/adr/ADR-0010-audit-log.md)). Вместо этого сессия SQLAlchemy
сама сообщает, что изменилось, а модель сама объявляет, что подлежит журналированию
(`Auditable`).

Импорт этого модуля **устанавливает обработчики** на класс сессии. Побочный эффект при
импорте — обычно дурной тон, но здесь он и есть смысл модуля: журнал, который надо не
забыть включить, однажды забудут включить. Поэтому модуль импортируется пакетом
`app.services`, а не отдельным вызовом при старте приложения.

Запись идёт в той же транзакции, что и само изменение: откат изменения откатывает и
запись о нём. Иначе журнал показывал бы правки, которых не было.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import event, insert, inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.base import NO_VALUE

from app.domain.audit import ActorKind, AuditAction, Changes, mask_changes
from app.observability import get_request_id
from app.repos.models.audit import Auditable, AuditLog

_PENDING = "orbita_pending_audit"


@dataclass(frozen=True, slots=True)
class Actor:
    """Кто действует в текущем запросе или задании."""

    id: uuid.UUID | None = None
    kind: ActorKind = ActorKind.JOB
    ip: str | None = None
    user_agent: str | None = None


_actor: ContextVar[Actor | None] = ContextVar("orbita_actor", default=None)


def set_actor(actor: Actor) -> None:
    _actor.set(actor)


def get_actor() -> Actor:
    """Кто действует сейчас.

    Никто не назвался — значит, фоновое задание. Так безопаснее, чем подставлять
    последнего известного человека: изменение, сделанное по расписанию, не должно
    выглядеть как чьё-то решение.
    """
    return _actor.get() or Actor()


@dataclass(slots=True)
class _Entry:
    """Отложенная запись: изменения известны до сохранения, идентификатор — после."""

    target: Any
    action: AuditAction
    changes: Changes = field(default_factory=dict)


def _plain(value: Any) -> Any:
    """Приводит значение к тому, что переживёт запись в JSONB и чтение обратно."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    return repr(value)


def _column_keys(target: Any) -> list[str]:
    return [attr.key for attr in inspect(type(target)).column_attrs]


def _changes_on_update(target: Any) -> Changes:
    """Только изменившиеся поля, как требует ADR-0010.

    Сравнение старого и нового значения делает сама SQLAlchemy: присвоение равного
    значения изменением не считается и записи не породит — даже когда объект другой,
    как бывает с датами после разбора запроса. Своей проверки здесь нет намеренно,
    дублировать чужую было бы мёртвым кодом; поведение закреплено тестами
    `test_assigning_the_same_value_is_not_a_change` и
    `test_equal_value_from_another_object_is_not_a_change`.
    """
    state = inspect(target)
    changes: Changes = {}
    for key in _column_keys(target):
        history = state.attrs[key].history
        if not history.has_changes():
            continue
        before = history.deleted[0] if history.deleted else None
        after = history.added[0] if history.added else None
        changes[key] = {"from": _plain(before), "to": _plain(after)}
    return changes


def _changes_on_create(target: Any) -> Changes:
    """Заполненные при создании поля.

    Здесь снимок уместен, а при изменении — нет: у новой записи «было» не существует,
    и без значений запись журнала сообщала бы только факт появления.
    """
    state = inspect(target)
    changes: Changes = {}
    for key in _column_keys(target):
        value = state.attrs[key].loaded_value
        if value is None or value is NO_VALUE:
            continue
        changes[key] = {"from": None, "to": _plain(value)}
    return changes


@event.listens_for(Session, "before_flush")
def _collect_changes(session: Session, flush_context: Any, instances: Any) -> None:
    """До сохранения: пока сессия ещё помнит, что именно изменилось."""
    pending: list[_Entry] = session.info.setdefault(_PENDING, [])

    for target in session.new:
        if isinstance(target, Auditable):
            pending.append(_Entry(target, AuditAction.CREATED, _changes_on_create(target)))

    for target in session.dirty:
        if not isinstance(target, Auditable):
            continue
        changes = _changes_on_update(target)
        if changes:
            pending.append(_Entry(target, AuditAction.UPDATED, changes))

    for target in session.deleted:
        if isinstance(target, Auditable):
            # Значения не записываются: деловые записи не удаляются, а уходят в архив
            # (ORB-025). Прямое удаление — событие, а не изменение содержимого.
            pending.append(_Entry(target, AuditAction.DELETED))


@event.listens_for(Session, "after_flush")
def _write_entries(session: Session, flush_context: Any) -> None:
    """После сохранения: у созданных записей появился идентификатор.

    Пишется Core-вставкой, а не добавлением объектов в сессию: объекты породили бы новый
    цикл сохранения, а вставка идёт по тому же соединению и в той же транзакции.
    """
    pending: list[_Entry] = session.info.pop(_PENDING, [])
    if not pending:
        return

    actor = get_actor()
    request_id = get_request_id()

    rows = [
        {
            "actor_id": actor.id,
            "actor_kind": actor.kind.value,
            "entity_type": entry.target.__tablename__,
            "entity_id": entry.target.id,
            "action": entry.action.value,
            "changes": (
                mask_changes(entry.changes) if entry.target.audit_is_classified else entry.changes
            ),
            "request_id": request_id,
            "ip": actor.ip,
            "user_agent": actor.user_agent,
        }
        for entry in pending
    ]
    session.execute(insert(AuditLog), rows)
