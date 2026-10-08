"""Модели данных.

Импортируются здесь целиком, чтобы попасть в `Base.metadata`: автогенерация Alembic видит
только те таблицы, чей модуль был загружен. Забытый импорт означает миграцию, которая
молча удаляет таблицу.
"""

from app.repos.models.access import AccessLink, Session
from app.repos.models.audit import Auditable, AuditLog
from app.repos.models.captures import Capture
from app.repos.models.checklists import TaskChecklistItem
from app.repos.models.comments import Comment
from app.repos.models.cycles import YearlyCycle
from app.repos.models.decisions import LeaderDecision, LeaderQuestion
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
from app.repos.models.files import PresentationVersion, SlideComment, StoredFile
from app.repos.models.ideas import Idea, IdeaMap, MapNode
from app.repos.models.ijro import (
    IjroAssignment,
    IjroControlMark,
    IjroDocument,
    IjroExtension,
    IjroImport,
    IjroOrgAlias,
    IjroPersonAlias,
)
from app.repos.models.interaction import Agreement, Letter
from app.repos.models.jobs import JobRun
from app.repos.models.milestones import Milestone
from app.repos.models.notifications import Notification
from app.repos.models.people import Person, User
from app.repos.models.preparations import InfoRequest, Preparation, PreparationItem
from app.repos.models.projects import Project, ProjectOrganization
from app.repos.models.push import PushSubscription
from app.repos.models.round import RoundMark
from app.repos.models.tasks import Task

__all__ = [
    "AccessLink",
    "Agreement",
    "AuditLog",
    "Auditable",
    "Capture",
    "Comment",
    "Direction",
    "Idea",
    "IdeaMap",
    "IjroAssignment",
    "IjroControlMark",
    "IjroDocument",
    "IjroExtension",
    "IjroImport",
    "IjroOrgAlias",
    "IjroPersonAlias",
    "InfoRequest",
    "JobRun",
    "LeaderDecision",
    "LeaderQuestion",
    "Letter",
    "MapNode",
    "Milestone",
    "Notification",
    "Organization",
    "Person",
    "Preparation",
    "PreparationItem",
    "PresentationVersion",
    "Project",
    "ProjectOrganization",
    "ProjectStatusRef",
    "ProjectTypeMilestone",
    "ProjectTypeRef",
    "PushSubscription",
    "Region",
    "RoundMark",
    "Session",
    "Setting",
    "SlideComment",
    "StoredFile",
    "Task",
    "TaskChecklistItem",
    "TaskStatusRef",
    "TaskTypeRef",
    "User",
    "YearlyCycle",
]
