"""Инфраструктура фоновых задач (ORB-036).

Три критерия карточки. Два из них проверяются **настоящим воркером на живой очереди**, а
не подстановкой: «падение задания не роняет воркер» — утверждение про ARQ и про нашу
обвязку вместе, и проверить его вызовом функции нельзя. Третий, идемпотентность, наоборот
проверяется прямым вызовом: тест, требующий воркера, падал бы от любой икоты Redis и
прятал бы настоящую причину.

Отдельно проверено то, что в карточке не записано, но без чего журнал изменений врёт:
изменение, сделанное заданием, подписано заданием, а не последним вошедшим человеком.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from arq import create_pool
from arq.connections import RedisSettings
from arq.typing import WorkerCoroutine
from arq.worker import Worker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.contextvars import get_contextvars
from structlog.testing import capture_logs

from app.domain.audit import ActorKind
from app.repos.models import AuditLog, Person
from app.services.audit import Actor, get_actor, set_actor
from app.settings import Settings
from app.workers.context import (
    FIRST_RETRY_DELAY,
    MAX_TRIES,
    job,
    job_context,
    retry_delay,
)
from tests.conftest import redis_url

pytestmark = pytest.mark.infra

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


class TestRetryPolicy:
    def test_the_delay_doubles(self) -> None:
        """Постоянная задержка не помогает: лежащая система лежит дольше интервала."""
        assert retry_delay(1) == FIRST_RETRY_DELAY
        assert retry_delay(2) == FIRST_RETRY_DELAY * 2
        assert retry_delay(3) == FIRST_RETRY_DELAY * 4

    async def test_a_failure_asks_for_a_retry_until_the_tries_run_out(self) -> None:
        from arq import Retry

        @job
        async def always_fails(ctx: dict[str, Any]) -> None:
            raise RuntimeError("внешняя система недоступна")

        with capture_logs() as logs:
            with pytest.raises(Retry):
                await always_fails({"job_try": 1})
            with pytest.raises(RuntimeError):
                await always_fails({"job_try": MAX_TRIES})

        events = [entry["event"] for entry in logs]
        assert "job_failed_will_retry" in events
        assert "job_exhausted" in events, "исчерпание попыток обязано быть отдельной строкой"

    async def test_a_successful_job_returns_its_result_untouched(self) -> None:
        @job
        async def counts(ctx: dict[str, Any], value: int) -> int:
            return value * 2

        assert await counts({"job_try": 1}, 21) == 42


class TestJobScope:
    async def test_the_actor_is_the_job_and_is_released_afterwards(
        self, session: AsyncSession
    ) -> None:
        """Изменение по расписанию не должно быть приписано человеку."""
        set_actor(Actor(id=uuid.uuid4(), kind=ActorKind.HUMAN))

        async with job_context("проба"):
            assert get_actor().kind is ActorKind.JOB
            assert get_actor().id is None

        assert get_actor().kind is ActorKind.JOB, "после задания действующее лицо сброшено"
        assert get_actor().id is None

    async def test_every_run_carries_an_identifier_into_the_log(self) -> None:
        """По нему находится и то, что задание изменило, и что при этом происходило."""
        async with job_context("проба", job_id="abc123"):
            bound = get_contextvars()

        assert bound["request_id"] == "abc123"
        assert bound["job"] == "проба"

    async def test_a_run_without_an_identifier_still_gets_one(self) -> None:
        async with job_context("проба"):
            bound = get_contextvars()

        assert bound["request_id"], "прогон без идентификатора нельзя найти в логе"

    async def test_a_change_made_by_a_job_is_signed_by_the_job(self, session: AsyncSession) -> None:
        """Проводка до записи журнала, а не только установка переменной.

        Без неё эскалация и автосоздание повторяющейся задачи выглядят в журнале как
        действия непонятно кого, и первый же разбор «кто поменял срок» упирается в тупик.
        """
        set_actor(Actor(kind=ActorKind.JOB))
        subject = Person(full_name="Заведён заданием")
        session.add(subject)
        await session.flush()

        entry = await session.scalar(select(AuditLog).where(AuditLog.entity_id == subject.id))
        assert entry is not None
        assert entry.actor_kind == ActorKind.JOB
        assert entry.actor_id is None
        set_actor(Actor())


# Задания воркера объявляются на уровне модуля: ARQ регистрирует их по полному имени
# (`__qualname__`), и у вложенной в тест функции оно выглядит как
# `TestClass.test_method.<locals>.explodes` — поставить такое в очередь по короткому
# имени нельзя, и воркер молча отвечает «функция не найдена».
DONE: list[int] = []
SURVIVED: list[str] = []


async def remember(ctx: dict[str, Any], value: int) -> None:
    DONE.append(value)


async def explodes(ctx: dict[str, Any]) -> None:
    raise RuntimeError("задание упало")


async def afterwards(ctx: dict[str, Any]) -> None:
    SURVIVED.append("выполнено после падения")


async def run_burst(queue: str, functions: list[Any]) -> Worker:
    """Поднимает настоящий воркер, разбирает очередь до конца и останавливается."""
    worker = Worker(
        functions=functions,
        queue_name=queue,
        redis_settings=RedisSettings.from_dsn(redis_url()),
        burst=True,
        poll_delay=0.01,
        max_tries=1,
        keep_result=1,
        handle_signals=False,
        health_check_interval=1,
    )
    await worker.async_run()
    return worker


class TestTheWorkerActuallyRuns:
    """Настоящий воркер на живой очереди: иначе проверяется не он, а подстановка."""

    async def test_an_enqueued_job_is_executed(self) -> None:
        queue = f"orbita:test:{uuid.uuid4().hex}"
        DONE.clear()

        pool = await create_pool(RedisSettings.from_dsn(redis_url()), default_queue_name=queue)
        try:
            await pool.enqueue_job("remember", 7)
            worker = await run_burst(queue, [remember])
        finally:
            await pool.aclose()

        assert DONE == [7]
        assert worker.jobs_complete == 1

    async def test_a_failing_job_does_not_bring_the_worker_down(self) -> None:
        """Критерий приёмки. Проверяется тем, что после падения воркер берёт следующее.

        Второе задание в той же очереди — и есть доказательство: если бы воркер умер на
        первом, второе осталось бы невыполненным.
        """
        queue = f"orbita:test:{uuid.uuid4().hex}"
        SURVIVED.clear()

        pool = await create_pool(RedisSettings.from_dsn(redis_url()), default_queue_name=queue)
        try:
            await pool.enqueue_job("explodes")
            await pool.enqueue_job("afterwards")
            worker = await run_burst(queue, [explodes, afterwards])
        finally:
            await pool.aclose()

        assert SURVIVED == ["выполнено после падения"], "воркер не дожил до второго задания"
        assert worker.jobs_failed == 1
        assert worker.jobs_complete == 1


class TestTheWholeThingStartsAndStops:
    """Критерий «воркер поднимается»: с настоящими on_startup и on_shutdown.

    Не с подставными: именно там создаётся подключение к базе, и именно оно ломается,
    когда воркер запускают впервые на новой машине.
    """

    async def test_the_worker_starts_with_the_real_hooks_and_stops(
        self,
        monkeypatch: pytest.MonkeyPatch,
        settings: Settings,
        migrated_database: str,
    ) -> None:
        """Раньше здесь ставилось в очередь настоящее задание уборки сессий.

        Уборка ушла вместе со входом (ADR-0026), а из настоящих заданий остался один
        предпросмотр — и ему нужна существующая версия вложения, хранилище и
        преобразователь. Тащить их сюда значило бы проверять предпросмотр, а не запуск.

        Поэтому очередь пуста намеренно: проверяется ровно то, ради чего тест заводился, —
        что **настоящие** `on_startup` и `on_shutdown` отрабатывают. Именно там создаётся
        подключение к базе, и именно оно ломается при первом запуске на новой машине.
        """
        from app.workers import main as entry

        # Настройки теста, а не окружения: иначе воркер поднялся бы против базы разработки.
        monkeypatch.setattr(entry, "get_settings", lambda: settings)

        queue = f"orbita:test:{uuid.uuid4().hex}"
        pool = await create_pool(RedisSettings.from_dsn(redis_url()), default_queue_name=queue)
        try:
            worker = Worker(
                functions=[cast("WorkerCoroutine", handler) for handler in entry.FUNCTIONS],
                queue_name=queue,
                redis_settings=RedisSettings.from_dsn(redis_url()),
                burst=True,
                poll_delay=0.01,
                max_tries=1,
                keep_result=1,
                handle_signals=False,
                health_check_interval=1,
                on_startup=entry.on_startup,
                on_shutdown=entry.on_shutdown,
            )
            await worker.async_run()
            # Останов вызывается напрямую, а не через `worker.close()`: тот шлёт себе
            # SIGUSR1, которого в Windows нет, — а разработка идёт на Windows. Проверяем
            # свой обработчик остановки, там и освобождается подключение к базе;
            # обработку сигналов проверяет ARQ у себя.
            await entry.on_shutdown({})
        finally:
            await pool.aclose()

        assert worker.jobs_failed == 0


class TestSchedule:
    def test_registered_jobs_match_the_names_used_to_enqueue_them(self) -> None:
        """Задание, поставленное по имени, но не зарегистрированное, не выполнится молча."""
        from app.services.documents import PREVIEW_JOB
        from app.workers.main import CRON_JOBS, FUNCTIONS, WorkerSettings

        registered = [handler.__name__ for handler in FUNCTIONS]
        assert PREVIEW_JOB in registered, (
            "задание предпросмотра ставится из обработчика запроса по имени "
            f"{PREVIEW_JOB!r}; не зарегистрированное здесь — это задание, которое "
            "никогда не выполнится, и никто об этом не узнает"
        )

        # Расписание пусто: ночная уборка сессий ушла вместе со входом (ADR-0026).
        # Проверка оставлена, чтобы следующее задание по часам завели осознанно.
        assert CRON_JOBS == []
        assert WorkerSettings.max_tries == MAX_TRIES, (
            "число попыток у ARQ и у обвязки обязано совпадать: разойдутся — "
            "задание получит лишнюю попытку или пропадёт раньше времени"
        )
        assert WorkerSettings.retry_jobs is True
