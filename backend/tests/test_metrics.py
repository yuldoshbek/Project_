"""Сервис показателей на настоящей базе: снимок, «что если», одни цифры везде.

Правило ступеней перебирается в `test_attention.py`; здесь — то, что видно только с
базой: перевод моментов в даты Ташкента, отбор незавершённого, признак жизни проекта и
главное обещание инварианта 2 — число в утренней сводке совпадает с Пультом, а «что
если» ничего не пишет.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attention import Attention
from app.domain.clock import local_date, now_utc
from app.domain.dictionaries import ProjectStatus
from app.jobs import run_job
from app.repos.models import AuditLog, LeaderQuestion
from app.services import metrics
from tests.factories import make_project, make_task

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")


def local_today() -> date:
    return local_date(now_utc(), TASHKENT)


class TestSnapshot:
    async def test_night_deadline_in_tashkent_is_not_overdue_in_the_morning(
        self, session: AsyncSession
    ) -> None:
        """Срок 26.09 03:00 по Ташкенту = 25.09 22:00 UTC. Утром 26.09 он горит, а не просрочен."""
        task = await make_task(session, due_at=datetime(2026, 9, 25, 22, 0, tzinfo=UTC))

        ladder = await metrics.ladder(session, today=date(2026, 9, 26), zone=TASHKENT)

        row = next(row for row in ladder.rows if row.entity_id == task.id)
        assert row.attention is Attention.BURNING
        assert row.due_on == date(2026, 9, 26)

    async def test_tasks_of_a_cancelled_project_are_not_in_the_ladder(
        self, session: AsyncSession
    ) -> None:
        """Работа закончена — спрашивать с её задач больше нечего, как и с её вех."""
        today = local_today()
        project = await make_project(
            session, due_on=today + timedelta(days=60), status=ProjectStatus.CANCELLED
        )
        task = await make_task(
            session,
            due_at=datetime.combine(today - timedelta(days=5), datetime.min.time(), UTC),
            project=project,
        )

        ladder = await metrics.ladder(session, today=today, zone=TASHKENT)

        assert task.id not in {row.entity_id for row in ladder.rows}
        assert ladder.on_track == 0

    async def test_new_project_without_tasks_is_not_silent(self, session: AsyncSession) -> None:
        """Признак жизни проекта включает сам проект: иначе новый «молчал» бы с первого дня."""
        today = local_today()
        await make_project(session, due_on=today + timedelta(days=120))

        ladder = await metrics.ladder(session, today=today, zone=TASHKENT)

        assert ladder.rows == ()
        assert ladder.on_track == 1

    async def test_open_question_lifts_the_project_to_the_top(self, session: AsyncSession) -> None:
        """«Ждёт решения» — открытый вопрос к руководителю, а не его собственное решение."""
        today = local_today()
        project = await make_project(session, due_on=today + timedelta(days=120))
        question = LeaderQuestion(
            target_type="project", target_id=project.id, text="Утвердить новый срок?"
        )
        session.add(question)
        await session.flush()

        asked = await metrics.ladder(session, today=today, zone=TASHKENT)
        assert asked.rows[0].entity_id == project.id
        assert asked.rows[0].attention is Attention.AWAITING_DECISION

        question.closed_at = now_utc()
        await session.flush()

        answered = await metrics.ladder(session, today=today, zone=TASHKENT)
        assert answered.rows == ()


class TestWhatIf:
    async def test_what_if_shows_the_effect_and_writes_nothing(self, session: AsyncSession) -> None:
        """Критерий 3 блока 1: влияние видно, база не меняется, пока не нажато «применить»."""
        today = local_today()
        project = await make_project(session, due_on=today + timedelta(days=90))
        await session.commit()
        entries_before = await session.scalar(select(func.count()).select_from(AuditLog))

        now, then = await metrics.what_if(
            session,
            today=today,
            zone=TASHKENT,
            changes={("projects", project.id): today - timedelta(days=1)},
        )

        assert now.on_track == 1
        assert then.rows[0].attention is Attention.OVERDUE
        assert not session.new and not session.dirty, "«что если» ничего не добавил в сессию"
        assert await session.scalar(select(func.count()).select_from(AuditLog)) == entries_before
        await session.refresh(project)
        assert project.due_on == today + timedelta(days=90)


class TestOneSetOfNumbers:
    async def test_morning_summary_equals_the_ladder(self, session: AsyncSession) -> None:
        """Сводка в 08:30 обязана совпасть с Пультом в 08:31 (инвариант 2)."""
        today = local_today()
        overdue = await make_project(session, due_on=today - timedelta(days=3))
        await make_project(session, due_on=today + timedelta(days=2))
        await make_project(session, due_on=today + timedelta(days=200))
        session.add(LeaderQuestion(target_type="project", target_id=overdue.id, text="Продлить?"))
        await session.flush()

        outcome = await run_job(session, "morning-summary", now=now_utc(), force=True)
        ladder = await metrics.ladder(session, today=today, zone=TASHKENT)

        assert outcome.result is not None
        assert outcome.result["awaiting_decision"] == ladder.count(Attention.AWAITING_DECISION) == 1
        assert outcome.result["burning"] == ladder.count(Attention.BURNING) == 1
        assert outcome.result["on_track"] == ladder.on_track == 1
        assert outcome.result["needs_attention"] == ladder.needs_attention
