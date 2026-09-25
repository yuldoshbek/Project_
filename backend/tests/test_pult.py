"""API Пульта: один запрос на экран, решение руководителя, вопрос помощника, отмена.

Главное здесь — три обещания экрана, утверждённого заказчиком 25.09.2026:

1. числа Пульта — те же, что считает сервис показателей (инвариант 2);
2. решение — одно касание руководителя, закрывает вопрос и попадает в журнал;
3. «Отменить» работает сразу после касания и только у автора.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.access import VISIT_GAP
from app.domain.attention import Attention
from app.domain.clock import local_date, now_utc
from app.domain.people import Role
from app.repos.models import AuditLog, LeaderDecision, LeaderQuestion, User
from app.repos.models import Session as SessionRecord
from app.services import access, metrics
from app.services.audit import Actor, set_actor
from app.services.decisions import UNDO_WINDOW
from app.settings import Settings
from tests.conftest import open_session_for
from tests.factories import make_person, make_project, make_task

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")
PULT = "/api/v1/pult"


def today() -> date:
    return local_date(now_utc(), TASHKENT)


async def ask(
    session: AsyncSession, project_id: object, text: str = "Утвердить?"
) -> LeaderQuestion:
    question = LeaderQuestion(target_type="project", target_id=project_id, text=text)
    session.add(question)
    await session.flush()
    return question


async def latest_session(session: AsyncSession) -> SessionRecord:
    leader = await session.scalar(select(User).where(User.role == Role.LEADER.value))
    assert leader is not None
    record = await session.scalar(
        select(SessionRecord)
        .where(SessionRecord.user_id == leader.id, SessionRecord.revoked_at.is_(None))
        .order_by(SessionRecord.expires_at.desc())
    )
    assert record is not None
    return record


class TestReading:
    async def test_numbers_are_the_metrics_numbers(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Пульт не считает сам: счётчики совпадают с сервисом показателей."""
        await make_project(session, due_on=today() - timedelta(days=2))
        await make_project(session, due_on=today() + timedelta(days=3))
        await make_project(session, due_on=today() + timedelta(days=200))

        body = (await leader_api.get(PULT)).json()
        ladder = await metrics.ladder(session, today=today(), zone=TASHKENT)

        for step in ("overdue", "burning", "awaiting_decision"):
            assert body["counts"][step] == ladder.count(Attention(step))
        assert body["on_track"] == ladder.on_track
        assert [row["entity_id"] for row in body["rows"]] == [
            str(row.entity_id) for row in ladder.rows
        ]

    async def test_row_carries_what_the_screen_shows(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Строка: кто держит, к чему относится, вопрос — одним ответом, без дозапросов."""
        karimov = await make_person(session, "Каримов А.")
        project = await make_project(
            session, due_on=today() + timedelta(days=100), responsible=karimov, title="Миссия"
        )
        await ask(session, project.id, "Перенести веху?")
        await make_task(
            session,
            due_at=datetime.now(UTC) - timedelta(days=3),
            project=project,
            assignee=karimov,
            title="Справка",
        )

        rows = (await leader_api.get(PULT)).json()["rows"]

        first, second = rows[0], rows[1]
        assert first["step"] == "awaiting_decision"
        assert first["question"]["text"] == "Перенести веху?"
        assert first["responsible"]["name"] == "Каримов А."
        assert (first["target_type"], first["target_id"]) == ("project", str(project.id))
        assert second["step"] == "overdue"
        assert second["context"] == "Миссия"

    async def test_screen_says_the_data_is_fictional_outside_production(
        self, leader_api: AsyncClient
    ) -> None:
        assert (await leader_api.get(PULT)).json()["is_demo"] is True


class TestDecisions:
    async def test_leader_decides_in_one_tap_and_the_question_closes(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=today() + timedelta(days=100))
        question = await ask(session, project.id)

        response = await leader_api.post(
            "/api/v1/decisions",
            json={"target_type": "project", "target_id": str(project.id), "kind": "approve"},
        )

        assert response.status_code == 201
        await session.refresh(question)
        assert question.closed_at is not None
        assert str(question.decision_id) == response.json()["id"]
        body = (await leader_api.get(PULT)).json()
        assert body["counts"]["awaiting_decision"] == 0

    async def test_decision_is_journaled(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Инвариант 5: и решение, и закрытие вопроса — в журнале изменений."""
        project = await make_project(session, due_on=today() + timedelta(days=100))
        question = await ask(session, project.id)

        decision_id = (
            await leader_api.post(
                "/api/v1/decisions",
                json={"target_type": "project", "target_id": str(project.id), "kind": "hurry"},
            )
        ).json()["id"]

        logged = {
            (entry.entity_type, str(entry.entity_id), entry.action)
            for entry in await session.scalars(select(AuditLog))
        }
        assert ("leader_decisions", decision_id, "created") in logged
        assert ("leader_questions", str(question.id), "updated") in logged

    async def test_assistant_cannot_decide(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Решение помощника от имени руководителя подписало бы журнал чужой рукой."""
        project = await make_project(session, due_on=today() + timedelta(days=100))

        response = await assistant_api.post(
            "/api/v1/decisions",
            json={"target_type": "project", "target_id": str(project.id), "kind": "approve"},
        )

        assert response.status_code == 403

    async def test_hurry_goes_to_whoever_holds_the_row(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """В одно касание руководитель не выбирает человека: торопят того, кто держит."""
        holder = await make_person(session, "Турсунов Б.")
        project = await make_project(
            session, due_on=today() - timedelta(days=1), responsible=holder
        )

        decision_id = (
            await leader_api.post(
                "/api/v1/decisions",
                json={"target_type": "project", "target_id": str(project.id), "kind": "hurry"},
            )
        ).json()["id"]

        decision = await session.get(LeaderDecision, decision_id)
        assert decision is not None
        assert decision.assignee_person_id == holder.id
        assert decision.state == "open", "«поторопить» ждёт исполнения"

    async def test_decision_on_a_missing_object_is_404(self, leader_api: AsyncClient) -> None:
        response = await leader_api.post(
            "/api/v1/decisions",
            json={
                "target_type": "project",
                "target_id": "00000000-0000-0000-0000-000000000000",
                "kind": "approve",
            },
        )
        assert response.status_code == 404


class TestUndo:
    async def test_undo_right_after_reopens_the_question(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=today() + timedelta(days=100))
        question = await ask(session, project.id)
        decision_id = (
            await leader_api.post(
                "/api/v1/decisions",
                json={"target_type": "project", "target_id": str(project.id), "kind": "approve"},
            )
        ).json()["id"]

        response = await leader_api.delete(f"/api/v1/decisions/{decision_id}")

        assert response.status_code == 204
        await session.refresh(question)
        assert question.closed_at is None
        assert (await leader_api.get(PULT)).json()["counts"]["awaiting_decision"] == 1

    async def test_late_undo_is_refused(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Позже решение не отменяется, а принимается новое: журнал решений не лжёт."""
        project = await make_project(session, due_on=today() + timedelta(days=100))
        decision_id = (
            await leader_api.post(
                "/api/v1/decisions",
                json={"target_type": "project", "target_id": str(project.id), "kind": "approve"},
            )
        ).json()["id"]
        decision = await session.get(LeaderDecision, decision_id)
        assert decision is not None
        decision.created_at = now_utc() - UNDO_WINDOW - timedelta(minutes=1)
        await session.flush()

        response = await leader_api.delete(f"/api/v1/decisions/{decision_id}")

        assert response.status_code == 422


class TestQuestions:
    async def test_assistant_asks_and_the_row_climbs_to_the_top(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=today() + timedelta(days=100))

        response = await assistant_api.post(
            "/api/v1/questions",
            json={"target_type": "project", "target_id": str(project.id), "text": "Решите?"},
        )

        assert response.status_code == 201
        rows = (await assistant_api.get(PULT)).json()["rows"]
        assert rows[0]["step"] == "awaiting_decision"
        assert rows[0]["question"]["text"] == "Решите?"

        undone = await assistant_api.delete(f"/api/v1/questions/{response.json()['id']}")
        assert undone.status_code == 204
        assert (await assistant_api.get(PULT)).json()["rows"] == []

    async def test_leader_does_not_ask_himself(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=today() + timedelta(days=100))

        response = await leader_api.post(
            "/api/v1/questions",
            json={"target_type": "project", "target_id": str(project.id), "text": "?"},
        )

        assert response.status_code == 403


class TestSinceLastVisit:
    async def test_changes_by_others_since_the_last_visit(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """«С прошлого визита» — чужие правки после отметки визита, а не журнал целиком."""
        project = await make_project(session, due_on=today() + timedelta(days=30), title="Атлас")
        leader = await session.scalar(select(User).where(User.role == Role.LEADER.value))
        assert leader is not None
        leader.last_visit_at = now_utc() - timedelta(hours=5)
        await session.commit()

        # Правка «чужими руками» — от имени задачи по расписанию, а не руководителя.
        set_actor(Actor())
        project.due_on = today() + timedelta(days=40)
        await session.commit()

        changes = (await leader_api.get(PULT)).json()["changes"]

        moved = [change for change in changes if change["kind"] == "deadline_moved"]
        assert moved and moved[0]["title"] == "Атлас"
        assert moved[0]["moved"]["to"] == (today() + timedelta(days=40)).isoformat()

    async def test_first_visit_has_nothing_to_compare_with(self, leader_api: AsyncClient) -> None:
        assert (await leader_api.get(PULT)).json()["changes"] == []


class TestVisits:
    async def test_a_break_starts_a_new_visit(
        self, session: AsyncSession, settings: Settings
    ) -> None:
        """После перерыва дольше двух часов конец прошлого визита запоминается."""
        token = await open_session_for(session, settings, Role.LEADER)
        record = await latest_session(session)
        previous = now_utc() - VISIT_GAP - timedelta(minutes=5)
        record.last_seen_at = previous
        await session.flush()

        user = await access.resolve(
            session, token=token, secret=settings.session_secret.get_secret_value(), now=now_utc()
        )

        assert user.last_visit_at == previous

    async def test_a_short_pause_is_the_same_visit(
        self, session: AsyncSession, settings: Settings
    ) -> None:
        token = await open_session_for(session, settings, Role.LEADER)
        record = await latest_session(session)
        record.last_seen_at = now_utc() - timedelta(minutes=40)
        await session.flush()

        user = await access.resolve(
            session, token=token, secret=settings.session_secret.get_secret_value(), now=now_utc()
        )

        assert user.last_visit_at is None
