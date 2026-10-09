"""Корневой роутер API.

Версия закреплена префиксом `/api/v1`: ломающее изменение получит новый префикс, а не
сломает работающий интерфейс.

**Роутеры разделов приходят вместе с экранами, которые их вызывают:** порядок работы —
сначала экран, заказчик его утверждает, потом API под утверждённый экран (CLAUDE.md, цикл
блока). Прежние сорок эндпоинтов были написаны раньше экранов, не получили ни одного
потребителя и ушли вместе со старой схемой (docs/audit/AUDIT-2026-09-20.md). Сейчас здесь
справочники, Пульт со сводкой, Программы, Проекты, Задачи, Календарь, Захват, Управление
и подписка на уведомления — экраны утверждены заказчиком 25–29.09.2026; Ижро — 30.09.2026;
Взаимодействие — 01.10.2026; Доклады и мероприятия — 05.10.2026; поиск по всем разделам —
блок 4, 09.10.2026.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.routes import (
    calendar,
    captures,
    decisions,
    dictionaries,
    files,
    ideas,
    ijro,
    interaction,
    management,
    preparations,
    programs,
    projects,
    pult,
    push,
    search,
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
api_router.include_router(pult.router)
api_router.include_router(decisions.router)
api_router.include_router(programs.router)
api_router.include_router(projects.router)
api_router.include_router(tasks.router)
api_router.include_router(calendar.router)
api_router.include_router(captures.router)
api_router.include_router(management.router)
api_router.include_router(push.router)
api_router.include_router(ijro.router)
api_router.include_router(interaction.router)
api_router.include_router(preparations.router)
api_router.include_router(ideas.router)
api_router.include_router(files.router)
api_router.include_router(search.router)
