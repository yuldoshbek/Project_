"""Корневой роутер API.

Версия закреплена префиксом `/api/v1`: ломающее изменение получит новый префикс, а не
сломает работающий интерфейс и бота (CLAUDE.md, сквозные правила).
"""

from __future__ import annotations

from fastapi import APIRouter

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX)

# Роутеры разделов подключаются здесь по мере готовности:
#   projects (ORB-011), tasks (ORB-014), calendar (ORB-026), dashboard (ORB-029),
#   briefing (ORB-061), search (ORB-033), integrations/google (ORB-057).
