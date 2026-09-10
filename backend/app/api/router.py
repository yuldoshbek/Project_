"""Корневой роутер API.

Версия закреплена префиксом `/api/v1`: ломающее изменение получит новый префикс, а не
сломает работающий интерфейс и бота (CLAUDE.md, сквозные правила).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import auth, dictionaries, milestones, projects, tasks

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(auth.router)
api_router.include_router(dictionaries.router)
api_router.include_router(projects.router)
api_router.include_router(tasks.router)
api_router.include_router(milestones.router)

# Роутеры разделов подключаются здесь по мере готовности:
#   calendar (ORB-026), dashboard (ORB-029),
#   briefing (ORB-061), search (ORB-033), integrations/google (ORB-057).
