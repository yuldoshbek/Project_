"""Модели данных.

Импортируются здесь целиком, чтобы попасть в `Base.metadata`: автогенерация Alembic видит
только те таблицы, чей модуль был загружен. Забытый импорт означает миграцию, которая
молча удаляет таблицу.
"""

from app.repos.models.access import AccessLink, Session
from app.repos.models.audit import Auditable, AuditLog
from app.repos.models.checklists import TaskChecklistItem
from app.repos.models.comments import Comment
from app.repos.models.cycles import YearlyCycle
from app.repos.models.decisions import LeaderDecision
from app.repos.models.dictionaries import (
    Direction,
    Organization,
    ProjectStatusRef,
    ProjectTypeMilestone,
    ProjectTypeRef,
    Region,
    Setting,
    TaskStatusRef,
    TaskTypeRef,
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
from app.repos.models.people import Person, User
from app.repos.models.projects import Project, ProjectOrganization
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
    "LeaderDecision",
    "Milestone",
    "Notification",
    "Organization",
    "Person",
    "Project",
    "ProjectOrganization",
    "ProjectStatusRef",
    "ProjectTypeMilestone",
    "ProjectTypeRef",
    "Region",
    "Session",
    "Setting",
    "Task",
    "TaskChecklistItem",
    "TaskStatusRef",
    "TaskTypeRef",
    "User",
    "YearlyCycle",
]
