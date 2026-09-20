"""Корневой роутер API.

Версия закреплена префиксом `/api/v1`: ломающее изменение получит новый префикс, а не
сломает работающий интерфейс и бота (CLAUDE.md, сквозные правила).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.routes import (
    checklists,
    comments,
    dictionaries,
    milestones,
    partners,
    people,
    projects,
    tasks,
)
from app.api.security import get_current_user

API_PREFIX = "/api/v1"

# Проверка доступа стоит здесь — один раз на все данные (ADR-0029). Забытая зависимость
# на отдельном пути незаметна на ревью, а открывает она всё, что этот путь отдаёт.
#
# Класс маршрута задаётся на каждом роутере отдельно, а не наследуется отсюда:
# `include_router` берёт класс у включаемого роутера, а не у включающего.
api_router = APIRouter(prefix=API_PREFIX, dependencies=[Depends(get_current_user)])
api_router.include_router(dictionaries.router)
api_router.include_router(people.router)
api_router.include_router(projects.router)
api_router.include_router(tasks.router)
api_router.include_router(checklists.router)
api_router.include_router(comments.router)
api_router.include_router(milestones.router)
api_router.include_router(partners.router)

# Роутеры разделов подключаются здесь по мере готовности блоков: программы, Ижро,
# взаимодействие, подготовка, идеи и карты, календарь, пульт (docs/PLAN.md).
