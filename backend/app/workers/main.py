"""Воркер фоновых задач.

Запускается как `arq app.workers.main.WorkerSettings` — цель `make worker`.

**Почему не в docker-compose.** Образа приложения в проекте нет: `docker-compose.yml`
поднимает только окружение — базу, Redis, хранилище и почту, — а backend и frontend
работают с хоста (`make dev`). Добавить сюда воркер отдельным контейнером означало бы
собрать образ приложения ради одного процесса и получить два разных способа запускать
один и тот же код. Воркер поднимается так же, как приложение: с хоста, командой. В CI он
поднимается по-настоящему — в тестах, в пакетном режиме, на живой очереди.

**Останов в Windows.** ARQ гасит воркер сигналом SIGUSR1, которого в Windows нет:
`Worker.close()` там падает с `AttributeError`. На рабочем контуре (Linux) это работает;
на машине разработчика воркер останавливают через Ctrl+C. Знать об этом надо заранее,
иначе первая же попытка остановить его выглядит как поломка нашего кода.
"""

from __future__ import annotations

from typing import Any

import structlog
from arq.connections import RedisSettings

from app.observability import configure_logging, route_library_logs
from app.repos.database import dispose_database, init_database
from app.settings import Settings, get_settings
from app.workers.context import MAX_TRIES
from app.workers.jobs import build_preview_job

logger = structlog.get_logger(__name__)

FUNCTIONS = [build_preview_job]

# Расписания нет. Единственное задание по часам — ночная чистка отзванных сессий —
# ушло вместе со входом (ADR-0026): сессий больше не существует. Список оставлен
# пустым, а не удалён: следующему заданию по расписанию будет куда встать.
CRON_JOBS: list[Any] = []


async def on_startup(ctx: dict[str, Any]) -> None:
    settings: Settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.use_json_logs)
    route_library_logs()
    init_database(settings)
    ctx["settings"] = settings
    logger.info("worker_started", jobs=[handler.__name__ for handler in FUNCTIONS])


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await dispose_database()
    logger.info("worker_stopped")


class WorkerSettings:
    """Настройки ARQ.

    `retry_jobs` включён, `max_tries` совпадает с тем, что знает обвязка задания: если
    развести эти числа, задание будет отчитываться об исчерпании попыток и получать ещё
    одну — или наоборот, молча пропадать раньше времени.
    """

    functions = FUNCTIONS
    cron_jobs = CRON_JOBS
    on_startup = staticmethod(on_startup)
    on_shutdown = staticmethod(on_shutdown)

    retry_jobs = True
    max_tries = MAX_TRIES

    # Задание, идущее дольше пяти минут, — это не задание, а забытый запрос: пусть падает
    # по таймауту и попадёт в лог, а не держит место в очереди до перезапуска воркера.
    job_timeout = 300

    # Результат хранится сутки: этого хватает, чтобы разобраться, почему задание упало,
    # и не хватает, чтобы Redis распух от истории.
    keep_result = 60 * 60 * 24

    health_check_interval = 30

    # Атрибут, а не метод: ARQ передаёт содержимое класса в конструктор как есть, и
    # функция уехала бы туда функцией. Настройки читаются при импорте — для точки входа
    # это нормально, а тесты подменяют их через `Worker(...)` напрямую.
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
