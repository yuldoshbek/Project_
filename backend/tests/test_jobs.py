"""Задачи по расписанию: секрет, идемпотентность, догоняющий режим.

Главное обещание здесь — **повторный вызов не делает работу дважды**. Расписание
доставляет запуск «по возможности» (ADR-0035): может пропустить, может позвать дважды,
может позвать две функции одновременно. Ошибка в этом месте выглядит как две утренние
сводки подряд — и это самая заметная для руководителя поломка из всех дешёвых.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import all_jobs, run_job
from app.jobs.registry import Job, JobContext, daily_period, register
from app.repos.models import JobRun
from app.settings import Settings

pytestmark = pytest.mark.infra

SECRET_HEADER = "X-Orbita-Jobs-Secret"


class TestRegistry:
    def test_the_three_jobs_of_the_schedule_are_registered(self) -> None:
        """Имена совпадают с расписанием в .github/workflows/jobs.yml.

        Расхождение здесь не падает: расписание получает 404, а сводка не приходит — и
        причину искать неделю.
        """
        assert set(all_jobs()) == {"morning-summary", "daily-snapshot", "deadline-check"}

    def test_every_job_has_a_period_and_a_title(self) -> None:
        for job in all_jobs().values():
            assert job.title
            assert job.period is not None


class TestIdempotency:
    async def test_the_first_run_does_the_work(self, session: AsyncSession) -> None:
        outcome = await run_job(session, "deadline-check", now=datetime(2026, 9, 20, 6, tzinfo=UTC))

        assert outcome.status == "done"
        assert outcome.skipped is False
        assert "overdue_tasks" in outcome.result

    async def test_the_second_run_in_the_same_period_does_nothing(
        self, session: AsyncSession
    ) -> None:
        """Так выглядит второй вызов расписания. Не ошибка — просто работа уже сделана."""
        moment = datetime(2026, 9, 20, 6, tzinfo=UTC)
        await run_job(session, "morning-summary", now=moment)

        again = await run_job(session, "morning-summary", now=moment + timedelta(minutes=7))

        assert again.skipped is True
        runs = list(await session.scalars(select(JobRun).where(JobRun.name == "morning-summary")))
        assert len(runs) == 1, "второй вызов завёл второй прогон — сводка ушла бы дважды"

    async def test_the_next_period_runs_again(self, session: AsyncSession) -> None:
        await run_job(session, "morning-summary", now=datetime(2026, 9, 20, 6, tzinfo=UTC))

        tomorrow = await run_job(
            session, "morning-summary", now=datetime(2026, 9, 21, 6, tzinfo=UTC)
        )

        assert tomorrow.skipped is False

    async def test_the_period_of_a_daily_job_is_local(self, session: AsyncSession) -> None:
        """Сутки считаются по Ташкенту: иначе граница дня проходит в пять утра по местному.

        22:00 UTC 20 сентября — это уже 03:00 21 сентября в Ташкенте, и сводка за это
        время относится к 21-му.
        """
        outcome = await run_job(
            session, "daily-snapshot", now=datetime(2026, 9, 20, 22, tzinfo=UTC)
        )

        assert outcome.period == "2026-09-21"


class TestFailures:
    async def test_an_unknown_job_is_not_found(self, session: AsyncSession) -> None:
        from app.domain.errors import NotFoundError

        with pytest.raises(NotFoundError) as error:
            await run_job(session, "нет-такой-задачи")

        assert "morning-summary" in str(error.value), "отказ обязан назвать, какие есть"

    async def test_a_failed_run_does_not_occupy_the_period(self, session: AsyncSession) -> None:
        """Одна ошибка не должна отменить задачу до конца суток.

        Прогон со статусом `failed` не считается сделанной работой: следующий вызов
        расписания пробует снова.
        """

        async def breaks(_: JobContext) -> dict[str, Any]:
            raise RuntimeError("проверочная поломка")

        name = "test-failing-job"
        if name not in all_jobs():
            register(Job(name=name, title="Проверочная", period=daily_period, handler=breaks))

        moment = datetime(2026, 9, 20, 6, tzinfo=UTC)
        with pytest.raises(RuntimeError):
            await run_job(session, name, now=moment)

        # Прогон откатился вместе с работой, поэтому период свободен: вторая попытка
        # доходит до обработчика, а не отвечает «уже сделано».
        with pytest.raises(RuntimeError):
            await run_job(session, name, now=moment + timedelta(minutes=5))


class TestTheEndpoint:
    async def test_the_schedule_runs_a_job_with_its_secret(
        self, api: AsyncClient, settings: Settings
    ) -> None:
        response = await api.post(
            "/internal/jobs/deadline-check",
            headers={SECRET_HEADER: settings.jobs_secret.get_secret_value()},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["job"] == "deadline-check"
        assert body["status"] == "done"

    async def test_without_the_secret_the_endpoint_says_nothing(self, api: AsyncClient) -> None:
        """401, а не 403: тот, кто пришёл без секрета, не «не имеет права», а не назвался."""
        response = await api.post("/internal/jobs/deadline-check")

        assert response.status_code == 401

    async def test_a_wrong_secret_is_refused(self, api: AsyncClient) -> None:
        response = await api.post(
            "/internal/jobs/deadline-check", headers={SECRET_HEADER: "wrong-secret-value-000"}
        )

        assert response.status_code == 401

    async def test_a_session_does_not_open_this_door(self, assistant_api: AsyncClient) -> None:
        """Личная ссылка не даёт права запускать задачи: это вход расписания, не человека."""
        response = await assistant_api.post("/internal/jobs/deadline-check")

        assert response.status_code == 401

    async def test_the_endpoint_is_outside_api(self, api: AsyncClient, settings: Settings) -> None:
        """Путь не начинается с `/api`, и через прокси интерфейса он недоступен (ADR-0028)."""
        through_proxy = await api.post(
            "/api/internal/jobs/deadline-check",
            headers={SECRET_HEADER: settings.jobs_secret.get_secret_value()},
        )

        assert through_proxy.status_code == 404
