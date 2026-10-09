"""Метка изменений (ADR-0034): экран перечитывает данные, только когда она сменилась.

Обещания:

1. без правок метка та же — опрос не тянет данные;
2. правка данных меняет метку — второй пользователь увидит её не позже следующего опроса;
3. смена дня меняет метку без правок — в полночь «горит» становится «просрочено».
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import now_utc
from app.repos import changes
from tests.factories import make_project

pytestmark = pytest.mark.infra

CHANGES = "/api/v1/changes"


async def test_same_without_changes(leader_api: AsyncClient) -> None:
    first = (await leader_api.get(CHANGES)).json()["stamp"]
    second = (await leader_api.get(CHANGES)).json()["stamp"]
    assert first == second


async def test_a_change_moves_the_stamp(
    leader_api: AsyncClient, assistant_api: AsyncClient
) -> None:
    """Помощник заводит задачу строкой — метка у руководителя другая."""
    before = (await leader_api.get(CHANGES)).json()["stamp"]
    created = await assistant_api.post(
        "/api/v1/captures", json={"kind": "task", "text": "Позвонить в Минфин"}
    )
    assert created.status_code == 201, created.text
    after = (await leader_api.get(CHANGES)).json()["stamp"]
    assert after != before


async def test_a_new_day_moves_the_stamp(session: AsyncSession) -> None:
    await make_project(session, due_on=now_utc().date() + timedelta(days=3))
    today = await changes.stamp(session, day="2026-10-09")
    tomorrow = await changes.stamp(session, day="2026-10-10")
    assert today != tomorrow


async def test_needs_a_link(api: AsyncClient) -> None:
    assert (await api.get(CHANGES)).status_code == 401
