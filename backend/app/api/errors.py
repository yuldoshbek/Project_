"""Единый формат ошибок — RFC 9457 (Problem Details for HTTP APIs).

Одна форма ответа на все виды отказов: и на доменную ошибку, и на неверный запрос, и на
падение. Интерфейс разбирает ответ одним кодом, а не гадает по форме тела.

Наружу не уходит ничего лишнего: текст исключения и стек остаются в логе. Сообщение об
ошибке — тоже поверхность выдачи данных: текст исключения базы называет таблицы,
ограничения и значения, а данные не покидают систему иначе как через выдачу, которую
для этого и писали.

**Конфликт записи — это 409, а не 500** (инвариант 15). Двое правят одно и то же чаще,
чем кажется: помощник вносит перенос срока ровно тогда, когда руководитель смотрит на
этот проект с телефона. Поле версии (`repos.base.Versioned`) превращает молчаливую
перезапись в `StaleDataError`, а ограничения базы — повтор и ссылку в пустоту — в
`IntegrityError`. Оба случая — не поломка, а «данные изменились, обновите и повторите»,
и человек должен прочитать именно это, а не «обратитесь к администратору».
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import (
    STALE_VERSION_MESSAGE,
    ConflictError,
    DomainError,
    ExternalServiceError,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
    RuleViolationError,
)
from app.observability import REQUEST_ID_HEADER, get_request_id, mask_secret_paths_in

PROBLEM_CONTENT_TYPE = "application/problem+json"

# Сопоставление доменных ошибок с кодами ответа. Единственное место, где предметная
# область встречается с протоколом.
STATUS_BY_ERROR: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    RuleViolationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    # Строго до PermissionDeniedError: сопоставление идёт по первому подходящему
    # типу в порядке объявления, а перестановка этих двух строк молча вернёт 403.
    NotAuthenticatedError: status.HTTP_401_UNAUTHORIZED,
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

# Один текст на оба пути: гонка внутри запроса (`StaleDataError`) и правка по старой
# версии (`StaleVersionError`) для человека — одно событие.
STALE_DATA_MESSAGE = STALE_VERSION_MESSAGE

# Код состояния SQLSTATE → что сказать человеку. Классы из стандарта SQL, одинаковые для
# любой установки PostgreSQL: https://www.postgresql.org/docs/16/errcodes-appendix.html
INTEGRITY_MESSAGES: dict[str, str] = {
    "23505": "Такая запись уже есть — повторить её нельзя",
    "23503": "Запись связана с другими данными: ссылка ведёт на удалённую запись или "
    "на эту запись ссылаются другие",
    "23514": "Данные нарушают правило, которое держит база",
    "23502": "Не заполнено обязательное поле",
}
INTEGRITY_FALLBACK = "Изменение противоречит данным, которые уже есть в системе"


def _integrity_details(error: IntegrityError) -> tuple[str | None, str | None]:
    """Код SQLSTATE и имя ограничения — для лога и выбора сообщения.

    Драйвер кладёт код в `sqlstate` обёртки, а имя ограничения — в исходное исключение
    asyncpg, которое лежит в `__cause__`. Ни то ни другое не обязано быть: исключение мог
    поднять не драйвер, а тест или другой диалект.
    """
    sqlstate = getattr(error.orig, "sqlstate", None)
    constraint = getattr(getattr(error.orig, "__cause__", None), "constraint_name", None)
    return (
        sqlstate if isinstance(sqlstate, str) else None,
        constraint if isinstance(constraint, str) else None,
    )


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
        # Путь отказа возвращается без токена личной ссылки: тело ответа читают
        # прокси и отчёты об ошибках, а ключу там не место (`app.observability`).
        body["instance"] = mask_secret_paths_in(instance)
    if errors:
        body["errors"] = errors

    headers: dict[str, str] = {}
    if status_code == status.HTTP_401_UNAUTHORIZED:
        # RFC 9110 (15.5.2) требует вызов при 401. Схема — `Cookie`, а не `Bearer`:
        # токена в заголовке у ORBITA нет, доступ даёт cookie сессии, которую ставит
        # личная ссылка (ADR-0029), и `Bearer` обещал бы вход, которого не существует.
        # Браузер на незнакомую схему окна входа не показывает — в отличие от `Basic`.
        headers["WWW-Authenticate"] = 'Cookie realm="ORBITA"'

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
            # Сообщение и подробность складываются, а не вытесняют друг друга. Раньше
            # подробность побеждала, и пользователь получал «начало 01.06, срок 01.05»
            # без объяснения, что именно не так. Подробность уточняет, а не заменяет.
            detail=f"{exc.message}: {exc.detail}" if exc.detail else exc.message,
            instance=request.url.path,
        )

    @app.exception_handler(StaleDataError)
    async def handle_stale_data(request: Request, exc: Exception) -> JSONResponse:
        # Сюда попадает и сбой фиксации в `api.transaction`: фиксация идёт внутри
        # обработчика маршрута, и её исключение проходит те же обработчики, что и
        # исключение из тела обработчика. Транзакцию откатывает `deps.get_session`.
        logger.info("stale_data", error=str(exc))
        return problem_response(
            status_code=status.HTTP_409_CONFLICT,
            code="stale-data",
            detail=STALE_DATA_MESSAGE,
            instance=request.url.path,
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, IntegrityError)
        sqlstate, constraint = _integrity_details(exc)
        # Имя ограничения — в лог, не в ответ: по нему разработчик находит правило за
        # секунды, а человеку оно ничего не говорит и выдаёт устройство базы.
        logger.info("integrity_conflict", sqlstate=sqlstate, constraint=constraint)
        return problem_response(
            status_code=status.HTTP_409_CONFLICT,
            code="integrity-conflict",
            detail=INTEGRITY_MESSAGES.get(sqlstate or "", INTEGRITY_FALLBACK),
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
