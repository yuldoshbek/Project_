"""Логи и сквозной идентификатор запроса.

Задача этого модуля — чтобы по сообщению пользователя «у меня не сохранилось» можно было
найти в логах ровно тот запрос. Для этого каждый запрос получает `request_id`, который
возвращается в заголовке ответа, попадает в тело ошибки и проставляется во все записи
лога, сделанные при обработке этого запроса.

Наши записи и записи библиотек проходят через один и тот же конвейер: библиотеки пишут
в стандартный `logging`, и без общей настройки их сообщения остались бы без `request_id`
и в другом формате — то есть бесполезными ровно тогда, когда нужны.

**Личная ссылка в журнал не попадает.** Путь `/api/access/{token}` — это и есть ключ:
кто прочитал его в логе, тот вошёл в систему на тридцать дней (ADR-0029). Поэтому токен
маскируется в трёх местах, и каждое закрывает свою дыру:

1. путь, который middleware кладёт в контекст каждой записи, маскируется на входе;
2. журнал доступа uvicorn (`"GET /api/access/… HTTP/1.1" 303`) маскируется фильтром на
   его логгере — фильтр висит на логгере, а не на обработчике, и срабатывает даже тогда,
   когда uvicorn подключил собственный обработчик мимо нашего;
3. любая строка любой записи, прошедшей через наш конвейер, проверяется ещё раз
   процессором `mask_secret_paths` — на случай, когда путь попал в сообщение иначе.

Журналы самих площадок (Vercel, Netlify) пишутся мимо приложения, и этот модуль их не
закрывает: путь запроса там видит площадка, а не наш код.
"""

from __future__ import annotations

import logging
import re
import sys
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

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
)

ACCESS_LOG_LOGGER = "uvicorn.access"

MASKED_TOKEN = "***"  # noqa: S105 — это заглушка вместо секрета, а не сам секрет

# Токен личной ссылки — всё, что стоит после `/api/access/` до конца сегмента. Соседние
# служебные пути (`/api/access/links/{role}`, `/api/access/sessions/{role}`) секрета не
# несут и остаются читаемыми: без этого в журнале не отличить перевыпуск от входа.
SECRET_PATH = re.compile(r"(/api/access/)(?!(?:links|sessions)/)[^/?#\s\"']+")


def mask_secret_paths_in(text: str) -> str:
    """Строка, в которой токен личной ссылки заменён на `***`."""
    return SECRET_PATH.sub(rf"\g<1>{MASKED_TOKEN}", text)


def _masked(value: Any) -> Any:
    return mask_secret_paths_in(value) if isinstance(value, str) else value


def mask_secret_paths(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Процессор structlog: последняя линия защиты для любой строки в записи.

    Стоит в общем конвейере, поэтому проверяет и наши записи, и записи библиотек — для
    них сообщение к этому моменту уже собрано в поле `event`.
    """
    for key, value in event_dict.items():
        event_dict[key] = _masked(value)
    return event_dict


class MaskSecretPaths(logging.Filter):
    """Фильтр стандартного `logging`: маскирует токен в сообщении и его аргументах.

    Журнал доступа uvicorn передаёт путь аргументом (`'%s - "%s %s HTTP/%s" %d'`), а не
    готовой строкой, поэтому проверяются и `msg`, и `args`. Запись не отбрасывается —
    факт входа в журнале нужен, не нужен только ключ.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _masked(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_masked(arg) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: _masked(value) for key, value in record.args.items()}
        return True


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
            # После сборки стека и перед отрисовкой: так проверяется всё, что уйдёт в
            # вывод, включая текст исключения, — и наши записи, и записи библиотек.
            mask_secret_paths,
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

    # Фильтр на самом логгере журнала доступа, а не на нашем обработчике: он срабатывает
    # до любого обработчика, в том числе подключённого uvicorn позже нас.
    access_log = logging.getLogger(ACCESS_LOG_LOGGER)
    if not any(isinstance(each, MaskSecretPaths) for each in access_log.filters):
        access_log.addFilter(MaskSecretPaths())


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
            # Путь попадает в каждую запись запроса — маскируется здесь, на входе, а не
            # в каждом месте, где что-то пишется в лог.
            path=mask_secret_paths_in(request.url.path),
        )
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
