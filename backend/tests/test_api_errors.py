"""Формат ошибок и сквозной идентификатор запроса.

Проверяется не «работает ли FastAPI», а два обещания каркаса: любая ошибка приходит в
одном формате, и по идентификатору из ответа находится запись в логе.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.domain.errors import (
    ConflictError,
    DomainError,
    ExternalServiceError,
    NotFoundError,
    PermissionDeniedError,
    RuleViolationError,
)
from app.observability import REQUEST_ID_HEADER, normalize_request_id

PROBLEM = "application/problem+json"


@pytest.fixture
def app_with_failing_routes(app: FastAPI) -> FastAPI:
    """Маршруты, существующие только ради проверки обработчиков ошибок."""

    @app.get("/_test/boom")
    async def boom() -> None:
        raise RuntimeError("секретная деталь устройства системы")

    @app.get("/_test/domain/{code}")
    async def domain(code: str) -> None:
        errors: dict[str, DomainError] = {
            "not-found": NotFoundError("проект не найден"),
            "conflict": ConflictError("статус уже изменён"),
            "rule": RuleViolationError("срок раньше даты начала"),
            "forbidden": PermissionDeniedError("только помощник может это менять"),
            "external": ExternalServiceError("Google не отвечает"),
        }
        raise errors[code]

    @app.get("/_test/validated")
    async def validated(number: int) -> dict[str, int]:
        return {"number": number}

    return app


async def test_health_is_not_a_problem(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class TestRequestId:
    async def test_returned_in_header(self, client: AsyncClient) -> None:
        response = await client.get("/health")

        assert response.headers[REQUEST_ID_HEADER]

    async def test_client_value_is_preserved(self, client: AsyncClient) -> None:
        response = await client.get("/health", headers={REQUEST_ID_HEADER: "abc-123"})

        assert response.headers[REQUEST_ID_HEADER] == "abc-123"

    def test_hostile_values_are_cleaned(self) -> None:
        """Заголовок приходит снаружи и попадает в лог — значит, чистится."""
        assert normalize_request_id("a b\nc") == "abc"
        assert normalize_request_id("") != ""
        assert normalize_request_id(None) != ""
        assert len(normalize_request_id("x" * 500)) == 64
        # Строка из одних недопустимых символов не должна давать пустой идентификатор.
        assert normalize_request_id("\n\t ") != ""


class TestProblemDetails:
    @pytest.mark.parametrize(
        ("route", "expected_status", "expected_code"),
        [
            ("not-found", 404, "not-found"),
            ("conflict", 409, "conflict"),
            ("rule", 422, "rule-violation"),
            ("forbidden", 403, "permission-denied"),
            ("external", 503, "external-service-unavailable"),
        ],
    )
    async def test_domain_errors_map_to_status(
        self,
        app_with_failing_routes: FastAPI,
        client: AsyncClient,
        route: str,
        expected_status: int,
        expected_code: str,
    ) -> None:
        response = await client.get(f"/_test/domain/{route}")

        assert response.status_code == expected_status
        assert response.headers["content-type"].startswith(PROBLEM)

        body = response.json()
        assert body["status"] == expected_status
        # Код стабилен: интерфейс и бот опираются на него, а не на текст сообщения.
        assert body["type"] == f"/problems/{expected_code}"
        assert body["title"]
        assert body["detail"]
        assert body["instance"] == f"/_test/domain/{route}"

    async def test_unhandled_error_hides_internals(
        self,
        app_with_failing_routes: FastAPI,
        client: AsyncClient,
    ) -> None:
        """Наружу — идентификатор запроса; текст исключения и стек остаются в логе."""
        response = await client.get("/_test/boom")

        assert response.status_code == 500
        assert response.headers["content-type"].startswith(PROBLEM)

        body = response.json()
        raw = response.text
        assert "секретная деталь" not in raw
        assert "RuntimeError" not in raw
        assert "Traceback" not in raw
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]

    async def test_validation_error_names_the_field(
        self,
        app_with_failing_routes: FastAPI,
        client: AsyncClient,
    ) -> None:
        response = await client.get("/_test/validated", params={"number": "не число"})

        assert response.status_code == 422
        assert response.headers["content-type"].startswith(PROBLEM)

        body = response.json()
        assert body["type"].endswith("validation-error")
        assert body["errors"], "ответ должен называть поля, а не только факт ошибки"
        assert body["errors"][0]["field"] == "number"

    async def test_unknown_path_is_a_problem_too(self, client: AsyncClient) -> None:
        """Единый формат означает единый: 404 от маршрутизатора выглядит так же."""
        response = await client.get("/такого-пути-нет")

        assert response.status_code == 404
        assert response.headers["content-type"].startswith(PROBLEM)
        assert response.json()["status"] == 404
