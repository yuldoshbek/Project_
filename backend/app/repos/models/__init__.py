"""Модели данных.

Импортируются здесь целиком, чтобы попасть в `Base.metadata`: автогенерация Alembic
видит только те таблицы, чей модуль был загружен. Забытый импорт означает миграцию,
которая молча удаляет таблицу.
"""

from app.repos.models.access import AccessLink, Session
from app.repos.models.audit import Auditable, AuditLog
from app.repos.models.checklists import Tag, TaskChecklistItem, TaskTag
from app.repos.models.comments import Comment
from app.repos.models.dictionaries import (
    Direction,
    Organization,
    PriorityRef,
    ProjectStatusRef,
    Setting,
    TaskStatusRef,
)
from app.repos.models.ijro import (
    IjroAssignment,
    IjroDocument,
    IjroImport,
    IjroOrgAlias,
    IjroPersonAlias,
)
from app.repos.models.jobs import JobRun
from app.repos.models.milestones import Milestone
from app.repos.models.notifications import Notification
from app.repos.models.partners import ProjectPartner
from app.repos.models.people import Person, User
from app.repos.models.projects import Project
from app.repos.models.tasks import Task

__all__ = [
    "AccessLink",
    "AuditLog",
    "Auditable",
    "Comment",
    "Direction",
    "IjroAssignment",
    "IjroDocument",
    "IjroImport",
    "IjroOrgAlias",
    "IjroPersonAlias",
    "JobRun",
    "Milestone",
    "Notification",
    "Organization",
    "Person",
    "PriorityRef",
    "Project",
    "ProjectPartner",
    "ProjectStatusRef",
    "Session",
    "Setting",
    "Tag",
    "Task",
    "TaskChecklistItem",
    "TaskStatusRef",
    "TaskTag",
    "User",
]
