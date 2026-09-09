"""Модели данных.

Импортируются здесь целиком, чтобы попасть в `Base.metadata`: автогенерация Alembic
видит только те таблицы, чей модуль был загружен. Забытый импорт означает миграцию,
которая молча удаляет таблицу.
"""

from app.repos.models.dictionaries import (
    Direction,
    Organization,
    PriorityRef,
    ProjectStatusRef,
    Setting,
    TaskStatusRef,
)
from app.repos.models.people import Person, User

__all__ = [
    "Direction",
    "Organization",
    "Person",
    "PriorityRef",
    "ProjectStatusRef",
    "Setting",
    "TaskStatusRef",
    "User",
]
