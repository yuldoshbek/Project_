"""Порт очереди фоновых заданий.

Ставит задание в очередь тот, кто обрабатывает запрос; выполняет — воркер. Между ними
Redis, и это единственное, что их связывает: приложение не знает, запущен ли воркер, а
воркер не знает, кто поставил задание.

**Задание откладывается на несколько секунд намеренно.** Запрос фиксирует транзакцию
*после* того, как отработал обработчик (`app.api.transaction`), — значит, поставленное из
обработчика задание успевает запуститься раньше, чем воркер сможет увидеть запись, ради
которой оно поставлено. Отсрочка закрывает этот разрыв, а повторная попытка задания
закрывает случай, когда фиксация почему-то задержалась дольше отсрочки. Одной отсрочки
мало: она делает гонку редкой, а не невозможной.

**Идентификатор задания собирается из того, что оно делает.** ARQ не ставит в очередь
второе задание с тем же идентификатором, пока первое не выполнено, — так двойное нажатие
не порождает двух преобразований одного файла (CLAUDE.md, инвариант 6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Protocol

import structlog
from arq import create_pool
from arq.connections import RedisSettings

from app.settings import Settings

logger = structlog.get_logger(__name__)

COMMIT_HEADROOM = timedelta(seconds=5)
"""Отсрочка по умолчанию — запас на фиксацию транзакции запроса."""


class JobQueue(Protocol):
    """Очередь заданий."""

    name: str

    async def enqueue(
        self, job: str, *args: Any, job_id: str | None = None, defer: timedelta | None = None
    ) -> None:
        """Ставит задание. Повтор с тем же `job_id` второго задания не создаёт."""
        ...


class RedisQueue:
    """Очередь ARQ поверх Redis."""

    name = "redis"

    def __init__(self, settings: Settings) -> None:
        self._settings = RedisSettings.from_dsn(settings.redis_url)

    async def enqueue(
        self, job: str, *args: Any, job_id: str | None = None, defer: timedelta | None = None
    ) -> None:
        pool = await create_pool(self._settings)
        try:
            await pool.enqueue_job(job, *args, _job_id=job_id, _defer_by=defer or COMMIT_HEADROOM)
        finally:
            await pool.aclose()


@dataclass(slots=True)
class RecordingQueue:
    """Очередь, которая ничего не выполняет и всё запоминает — для тестов.

    Проверять «задание поставлено» на поднятом Redis значит проверять заодно Redis;
    проверять «преобразование произошло» — вызовом самого задания, напрямую.
    """

    name: str = "recording"
    jobs: list[tuple[str, tuple[Any, ...], str | None]] = field(default_factory=list)

    async def enqueue(
        self, job: str, *args: Any, job_id: str | None = None, defer: timedelta | None = None
    ) -> None:
        self.jobs.append((job, args, job_id))


def create_job_queue(settings: Settings) -> JobQueue:
    """Очередь по настройкам. Реализация одна — ARQ поверх того же Redis, что и всё прочее."""
    return RedisQueue(settings)
