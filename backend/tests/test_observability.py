"""Логи.

Здесь проверяется не красота вывода, а работоспособность: логгер, который падает при
вызове, хуже отсутствующего — он превращает любую обработанную ошибку в пустой 500.
Именно это и случилось при первой реализации, поэтому тесты ниже существуют.
"""

from __future__ import annotations

import io
import json
import logging

import structlog

from app.observability import (
    LIBRARY_LOGGERS,
    configure_logging,
    route_library_logs,
)


def capture(json_output: bool = True) -> io.StringIO:
    """Настраивает логи и подменяет поток вывода, сохраняя формат."""
    configure_logging(level="INFO", json_output=json_output)
    stream = io.StringIO()
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(stream)
    return stream


def test_logging_does_not_raise() -> None:
    """Регрессия: с PrintLogger падал `add_logger_name`, и рушился каждый вызов.

    Проявлялось это не в логах, а в ответах: обработчик ошибки не мог записать событие,
    исключение уходило в обработчик верхнего уровня, и наружу приходил пустой 500.
    """
    stream = capture()

    structlog.get_logger("проверка").info("событие", ключ="значение")

    record = json.loads(stream.getvalue())
    assert record["event"] == "событие"
    assert record["ключ"] == "значение"
    assert record["logger"] == "проверка"
    assert record["level"] == "info"
    assert record["timestamp"]


def test_exception_is_logged_with_traceback() -> None:
    """Стек обязан быть в логе — наружу он не уходит (ADR: единый формат ошибок)."""
    stream = capture()

    try:
        raise RuntimeError("подробность для журнала")
    except RuntimeError:
        structlog.get_logger("проверка").exception("unhandled_error")

    record = json.loads(stream.getvalue())
    assert record["event"] == "unhandled_error"
    assert "подробность для журнала" in record["exception"]
    assert "Traceback" in record["exception"]


def test_context_is_attached_to_every_record() -> None:
    """Идентификатор запроса должен попадать во все записи, а не только в свою."""
    stream = capture()
    structlog.contextvars.bind_contextvars(request_id="abc123")

    try:
        structlog.get_logger("проверка").info("первое")
        structlog.get_logger("другой").warning("второе")
    finally:
        structlog.contextvars.clear_contextvars()

    records = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    assert [record["request_id"] for record in records] == ["abc123", "abc123"]


def test_library_logs_join_the_common_pipeline() -> None:
    """Записи uvicorn и SQLAlchemy должны выглядеть так же, как наши, иначе их не собрать."""
    stream = capture()

    # Библиотека завела собственный обработчик — типичное поведение uvicorn при старте.
    uvicorn_logger = logging.getLogger("uvicorn.access")
    uvicorn_logger.handlers = [logging.StreamHandler(io.StringIO())]
    uvicorn_logger.propagate = False

    route_library_logs()
    uvicorn_logger.info("GET /health 200")

    record = json.loads(stream.getvalue())
    assert record["event"] == "GET /health 200"
    assert record["logger"] == "uvicorn.access"


def test_console_format_is_readable() -> None:
    """В разработке вывод читается глазами, а не разбирается парсером."""
    stream = capture(json_output=False)

    structlog.get_logger("проверка").info("запуск", env="development")

    line = stream.getvalue()
    assert "запуск" in line
    assert "env=development" in line
    assert not line.lstrip().startswith("{")


def test_library_list_covers_what_we_actually_use() -> None:
    """Список библиотек — не декорация: пропущенная пишет мимо общего формата."""
    assert "uvicorn.access" in LIBRARY_LOGGERS
    assert "sqlalchemy.engine" in LIBRARY_LOGGERS
    assert "arq" in LIBRARY_LOGGERS
