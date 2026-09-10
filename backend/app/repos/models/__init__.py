"""Модели данных.

Импортируются здесь целиком, чтобы попасть в `Base.metadata`: автогенерация Alembic
видит только те таблицы, чей модуль был загружен. Забытый импорт означает миграцию,
которая молча удаляет таблицу.
"""

from app.repos.models.audit import Auditable, AuditLog
from app.repos.models.auth import RefreshToken
from app.repos.models.dictionaries import (
    Direction,
    Organization,
    PriorityRef,
    ProjectStatusRef,
    Setting,
    TaskStatusRef,
)
from app.repos.models.milestones import Milestone
from app.repos.models.people import Person, User
from app.repos.models.projects import Project
from app.repos.models.tasks import Task

__all__ = [
    "AuditLog",
    "Auditable",
    "Direction",
    "Milestone",
    "Organization",
    "Person",
    "PriorityRef",
    "Project",
    "ProjectStatusRef",
    "RefreshToken",
    "Setting",
    "Task",
    "TaskStatusRef",
    "User",
]
