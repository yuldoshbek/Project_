"""Живость и готовность.

Разделение принципиальное: `/api/health` не должен зависеть от базы, иначе её
недоступность приведёт к перезапуску исправного приложения — и так по кругу, пока база не
вернётся.

Путь начинается с `/api`, потому что интерфейс проксирует на API только его (ADR-0028):
проверка, доступная мимо прокси, проверяла бы не тот путь, которым ходят люди.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.repos.database import dispose_database, get_engine, init_database
from app.settings import Settings


async def test_health_does_not_touch_dependencies(client: AsyncClient) -> None:
    """Проверка живости отвечает, даже когда зависимости лежат.

    Подключение к базе намеренно снято перед запросом.
    """
    await dispose_database()

    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_health_names_the_deployed_commit(client: AsyncClient) -> None:
    """Выкладка сверяет этот коммит с тем, что выкладывала (deploy.yml).

    Без него успешной выкладкой считается кеш прежней сборки: адрес отвечает, а код на нём
    старый — и понять это можно только по поведению, то есть уже от руководителя.
    """
    response = await client.get("/api/health")

    body = response.json()
    assert body["commit"]
    assert body["env"] == "test"
    assert body["time"]


@pytest.mark.infra
async def test_ready_when_everything_is_up(client: AsyncClient) -> None:
    response = await client.get("/api/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": "ok"}


async def test_ready_returns_503_and_names_the_culprit(settings: Settings) -> None:
    """Недоступность базы — это 503 с указанием, что именно не отвечает.

    Порт заведомо свободен: ответ должен получиться быстро и без зависания.
    """
    broken = settings.model_copy(update={"db_host": "127.0.0.1", "db_port": 1})
    application = create_app(broken)
    init_database(broken)
    try:
        transport = ASGITransport(app=application, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="https://test") as http_client:
            response = await http_client.get("/api/ready")
    finally:
        await dispose_database()

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert "недоступна" in body["checks"]["database"]


@pytest.mark.infra
async def test_lifespan_opens_and_closes_database(settings: Settings) -> None:
    """Подключение создаётся на старте приложения, а не при первом запросе.

    Иначе первый запрос после выкладки ждёт подключения, и это ровно тот запрос, который
    делает руководитель, открыв систему с телефона.
    """
    application = create_app(settings)

    async with application.router.lifespan_context(application):
        assert get_engine() is not None
