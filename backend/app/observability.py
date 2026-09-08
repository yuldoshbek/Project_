"""Логи и сквозной идентификатор запроса.

Задача этого модуля — чтобы по сообщению пользователя «у меня не сохранилось» можно было
найти в логах ровно тот запрос. Для этого каждый запрос получает `request_id`, который
возвращается в заголовке ответа, попадает в тело ошибки и проставляется во все записи
лога, сделанные при обработке этого запроса.

Наши записи и записи библиотек проходят через один и тот же конвейер: библиотеки пишут
в стандартный `logging`, и без общей настройки их сообщения остались бы без `request_id`
и в другом формате — то есть бесполезными ровно тогда, когда нужны.
"""

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

# Ограничение длины: заголовок приходит снаружи, и без предела в лог попадёт всё, что
# отправитель захочет туда записать.
MAX_REQUEST_ID_LENGTH = 64

# Библиотеки, которые заводят собственные обработчики и по умолчанию не пропускают
# записи в корневой логгер. Без вмешательства их сообщения идут мимо нашего формата.
LIBRARY_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "sqlalchemy.engine",
    "arq",
)


def configure_logging(*, level: str = "INFO", json_output: bool = False) -> None:
    """Настраивает structlog поверх стандартного logging.

    Обработка идёт в два шага: structlog собирает событие, `ProcessorFormatter`
    отрисовывает его на выходе стандартного обработчика. Записи библиотек проходят
    тот же путь — см. `route_library_logs`.
    """
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        # Именно stdlib-фабрика, а не PrintLogger: последний не имеет имени, и
        # add_logger_name роняет каждый вызов логгера. Проверяется в test_observability.
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.getLevelNamesMapping().get(level.upper(), logging.INFO))

    route_library_logs()


def route_library_logs() -> None:
    """Направляет логи библиотек в общий конвейер.

    Вызывается дважды: при настройке и повторно при старте приложения. Второй раз
    обязателен — uvicorn применяет собственную конфигурацию логов уже после импорта
    модуля, и без повторного вызова его записи о запросах выглядят иначе, чем все
    остальные, и не попадают в сбор логов вместе с ними.
    """
    for name in LIBRARY_LOGGERS:
        library_logger = logging.getLogger(name)
        library_logger.handlers = []
        library_logger.propagate = True


def normalize_request_id(raw: str | None) -> str:
    """Берёт идентификатор из заголовка или создаёт новый.

    Значение приходит от клиента, поэтому обрезается по длине и очищается от всего, кроме
    безопасного набора символов: строка попадает в лог, а лог читают глазами и
    инструментами.
    """
    if not raw:
        return uuid.uuid4().hex

    cleaned = "".join(char for char in raw if char.isalnum() or char in "-_")
    return cleaned[:MAX_REQUEST_ID_LENGTH] or uuid.uuid4().hex


def get_request_id() -> str | None:
    """Идентификатор текущего запроса, если он есть."""
    value = structlog.contextvars.get_contextvars().get("request_id")
    return value if isinstance(value, str) else None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Привязывает `request_id` к запросу и возвращает его в заголовке ответа."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER))

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
