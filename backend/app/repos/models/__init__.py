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

__all__ = [
    "Direction",
    "Organization",
    "PriorityRef",
    "ProjectStatusRef",
    "Setting",
    "TaskStatusRef",
]
