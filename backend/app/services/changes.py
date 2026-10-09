"""Метка изменений для опроса экранов (ADR-0034): читается из `app.repos.changes`."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import local_date
from app.repos import changes as read_model


async def stamp(session: AsyncSession, *, now: datetime, zone: ZoneInfo) -> str:
    return await read_model.stamp(session, day=local_date(now, zone).isoformat())
