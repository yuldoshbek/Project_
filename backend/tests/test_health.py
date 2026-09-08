"""Живость и готовность.

Разделение принципиальное: `/health` не должен зависеть от базы, иначе её недоступность
приведёт к перезапуску исправного приложения — и так по кругу, пока база не вернётся.
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

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.infra
async def test_ready_when_everything_is_up(client: AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": "ok", "redis": "ok"}


async def test_ready_returns_503_and_names_the_culprit(settings: Settings) -> None:
    """Недоступность зависимостей — это 503 с указанием, что именно не отвечает.

    Порты заведомо свободны: ответ должен получиться быстро и без зависания.
    """
    broken = settings.model_copy(
        update={
            "db_host": "127.0.0.1",
            "db_port": 1,
            "redis_url": "redis://127.0.0.1:1/0",
        }
    )
    application = create_app(broken)
    init_database(broken)
    try:
        transport = ASGITransport(app=application, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            response = await http_client.get("/ready")
    finally:
        await dispose_database()

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"].startswith("недоступна")
    assert body["checks"]["redis"].startswith("недоступен")


@pytest.mark.infra
async def test_lifespan_opens_and_closes_database(settings: Settings) -> None:
    """Приложение само поднимает подключение при старте и закрывает при остановке.

    Остальные тесты делают это вручную, потому что `ASGITransport` lifespan не
    выполняет. Здесь проверяется настоящий путь запуска — тот, по которому пойдёт
    uvicorn.
    """
    application = create_app(settings)

    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            response = await http_client.get("/ready")

    assert response.json()["checks"]["database"] == "ok"

    # После остановки движок закрыт: обращение к нему обязано сказать об этом внятно,
    # а не упасть где-то в глубине драйвера.
    with pytest.raises(RuntimeError, match="движок не создан"):
        get_engine()


def test_secret_is_absent_from_openapi(settings: Settings) -> None:
    """Схема API отдаётся наружу — в ней не должно оказаться ничего из настроек."""
    schema = create_app(settings).openapi()

    assert "test-secret-not-for-production" not in str(schema)
    assert schema["info"]["title"] == "ORBITA"
