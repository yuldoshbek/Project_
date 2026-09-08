"""Единый формат ошибок — RFC 9457 (Problem Details for HTTP APIs).

Одна форма ответа на все виды отказов: и на доменную ошибку, и на неверный запрос, и на
падение. Интерфейс и бот разбирают ответ одним кодом, а не гадают по форме тела.

Наружу не уходит ничего лишнего: текст исключения и стек остаются в логе. Сообщение об
ошибке — тоже поверхность выдачи данных, и на ней действует то же правило, что и везде
(CLAUDE.md, инвариант 1).
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import (
    ConflictError,
    DomainError,
    ExternalServiceError,
    NotFoundError,
    PermissionDeniedError,
    RuleViolationError,
)
from app.observability import REQUEST_ID_HEADER, get_request_id

PROBLEM_CONTENT_TYPE = "application/problem+json"

# Сопоставление доменных ошибок с кодами ответа. Единственное место, где предметная
# область встречается с протоколом.
STATUS_BY_ERROR: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    RuleViolationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    ExternalServiceError: status.HTTP_503_SERVICE_UNAVAILABLE,
}

TITLE_BY_STATUS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Некорректный запрос",
    status.HTTP_401_UNAUTHORIZED: "Требуется вход в систему",
    status.HTTP_403_FORBIDDEN: "Действие недоступно",
    status.HTTP_404_NOT_FOUND: "Запись не найдена",
    status.HTTP_409_CONFLICT: "Действие противоречит текущему состоянию",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "Данные не прошли проверку",
    status.HTTP_429_TOO_MANY_REQUESTS: "Слишком много запросов",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "Внутренняя ошибка",
    status.HTTP_503_SERVICE_UNAVAILABLE: "Сервис временно недоступен",
}


def problem_response(
    *,
    status_code: int,
    code: str,
    detail: str | None = None,
    instance: str | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"/problems/{code}",
        "title": TITLE_BY_STATUS.get(status_code, "Ошибка"),
        "status": status_code,
    }
    if detail:
        body["detail"] = detail
    if instance:
        body["instance"] = instance
    if errors:
        body["errors"] = errors

    headers: dict[str, str] = {}
    request_id = get_request_id()
    if request_id:
        # Пользователь называет этот идентификатор — по нему находится запись в логе.
        body["request_id"] = request_id
        # Заголовок проставляется здесь, а не только в middleware: ответ на необработанное
        # исключение собирается уровнем выше неё (ServerErrorMiddleware), и до middleware
        # управление уже не возвращается. Именно на таких ответах идентификатор и нужен.
        headers[REQUEST_ID_HEADER] = request_id

    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    logger = structlog.get_logger(__name__)

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DomainError)
        status_code = next(
            (code for error_type, code in STATUS_BY_ERROR.items() if isinstance(exc, error_type)),
            status.HTTP_400_BAD_REQUEST,
        )
        logger.info(
            "domain_error",
            code=exc.code,
            status=status_code,
            message=exc.message,
        )
        return problem_response(
            status_code=status_code,
            code=exc.code,
            detail=exc.detail or exc.message,
            instance=request.url.path,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        errors = [
            {
                "field": ".".join(str(part) for part in error["loc"][1:]) or str(error["loc"][0]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return problem_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation-error",
            detail="Проверьте заполнение полей",
            instance=request.url.path,
            errors=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        return problem_response(
            status_code=exc.status_code,
            code=f"http-{exc.status_code}",
            detail=str(exc.detail) if exc.detail else None,
            instance=request.url.path,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Стек остаётся здесь, в логе. Наружу уходит только идентификатор запроса:
        # текст исключения выдаёт устройство системы, а её ищут снаружи именно так.
        logger.exception("unhandled_error", error_type=type(exc).__name__)
        return problem_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal-error",
            detail="Обратитесь к администратору и назовите идентификатор запроса",
            instance=request.url.path,
        )
