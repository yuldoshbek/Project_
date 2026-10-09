"""Метка изменений — то, что экран спрашивает раз в 15 секунд вместо данных (ADR-0034).

Ответ — одна строка. Совпала с прошлой — экран ничего не перечитывает; сменилась —
перечитывает данные разделов, которые сейчас на экране. Так опрос стоит один лёгкий
запрос, а не сборку Пульта целиком (`frontend/src/shared/api/changes.ts`).
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.api.deps import SessionDep, SettingsDep
from app.api.transaction import transactional_router
from app.domain.clock import now_utc
from app.services import changes as service

router = transactional_router(tags=["служебные"])


class ChangesOut(BaseModel):
    stamp: str


@router.get("/changes", response_model=ChangesOut, summary="Метка изменений для опроса")
async def read_changes(session: SessionDep, settings: SettingsDep) -> ChangesOut:
    return ChangesOut(
        stamp=await service.stamp(session, now=now_utc(), zone=ZoneInfo(settings.timezone))
    )
