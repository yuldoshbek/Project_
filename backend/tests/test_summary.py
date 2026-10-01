"""Утренняя сводка: вкладка «Сводка» Пульта, подписка устройства, пуш о вопросе (ТЗ 8).

Три обещания экрана, утверждённого заказчиком 29.09.2026:

1. списки сводки — строки той же лестницы, что на Пульте (инвариант 2), а экран
   блокировки — ровно то, что уйдёт в пуш;
2. уведомления включает руководитель на своём устройстве (V28);
3. вопрос помощника приходит руководителю пушем сразу после записи (V27), а отказ службы
   уведомлений не отменяет вопрос.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.push import PushOutcome
from app.domain.attention import Attention
from app.domain.clock import local_date, now_utc
from app.domain.people import Role
from app.domain.push import summary_key
from app.repos.models import LeaderQuestion, Notification, PushSubscription, Setting, User
from app.services import metrics
from tests.factories import make_project, make_task
from tests.fakes import FAKE_PUBLIC_KEY, FakePushSender

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")
SUMMARY = "/api/v1/pult/summary"
SUBSCRIPTION = "/api/v1/push/subscription"
IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


P256DH = b64url(b"\x04" + bytes(range(64)))
AUTH = b64url(bytes(range(16)))
ENDPOINT = "https://web.push.apple.com/QGuQyavXutnMfDk"


def today() -> date:
    return local_date(now_utc(), TASHKENT)


def at_noon(day: date) -> datetime:
    return datetime.combine(day, time(12), TASHKENT)


async def leader_of(session: AsyncSession) -> User:
    leader = await session.scalar(select(User).where(User.role == Role.LEADER.value))
    assert leader is not None
    return leader


async def ask(session: AsyncSession, target_type: str, target_id: object) -> None:
    session.add(LeaderQuestion(target_type=target_type, target_id=target_id, text="Решите?"))
    await session.flush()


async def subscribe_leader(
    session: AsyncSession,
    *,
    endpoint: str = ENDPOINT,
    device: str = "iPhone",
    created_at: datetime | None = None,
) -> PushSubscription:
    leader = await leader_of(session)
    record = PushSubscription(
        user_id=leader.id, endpoint=endpoint, p256dh=P256DH, auth=AUTH, device=device
    )
    if created_at is not None:
        record.created_at = created_at
    session.add(record)
    await session.flush()
    return record


def subscription_body(endpoint: str = ENDPOINT, **keys: str) -> dict[str, object]:
    return {
        "endpoint": endpoint,
        "expirationTime": None,
        "keys": {"p256dh": keys.get("p256dh", P256DH), "auth": keys.get("auth", AUTH)},
    }


class TestTheSummary:
    async def test_both_roles_see_the_same_summary(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        """Руководитель смотрит, что придёт; помощник — пришла ли. Данные одни (инв. 13)."""
        leader = await leader_api.get(SUMMARY)
        assistant = await assistant_api.get(SUMMARY)

        assert leader.status_code == assistant.status_code == 200
        assert leader.json()["awaiting"] == assistant.json()["awaiting"] == []
        assert leader.json()["is_demo"] is True

    async def test_the_lists_are_the_rows_of_the_ladder(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """«Ждёт решения» — ступень лестницы, «срок сегодня» — её строки со сроком сегодня
        на любой ступени (V26): строка, ждущая решения, со сроком сегодня — в обоих."""
        waiting = await make_project(session, due_on=today() + timedelta(days=100))
        await ask(session, "project", waiting.id)
        await make_project(session, due_on=today())
        await make_project(session, due_on=today() - timedelta(days=3))
        both = await make_task(session, due_at=at_noon(today()), title="Справка к сроку")
        await ask(session, "task", both.id)

        body = (await leader_api.get(SUMMARY)).json()
        ladder = await metrics.ladder(session, today=today(), zone=TASHKENT)

        assert [row["entity_id"] for row in body["awaiting"]] == [
            str(row.entity_id) for row in ladder.of(Attention.AWAITING_DECISION)
        ]
        assert [row["entity_id"] for row in body["due_today"]] == [
            str(row.entity_id) for row in metrics.due_today(ladder, today())
        ]
        assert len(body["awaiting"]) == 2
        assert len(body["due_today"]) == 2
        assert str(both.id) in {row["entity_id"] for row in body["awaiting"]}
        assert str(both.id) in {row["entity_id"] for row in body["due_today"]}
        assert body["awaiting"][0]["question"]["text"] == "Решите?"

    async def test_the_first_due_row_does_not_depend_on_the_database(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Равные строки идут по названию: экран блокировки не меняет первую строку от
        того, в каком порядке база отдала записи."""
        await make_task(session, due_at=at_noon(today()), title="Бюджет на квартал")
        await make_task(session, due_at=at_noon(today()), title="Акт приёмки")

        body = (await leader_api.get(SUMMARY)).json()

        assert [row["title"] for row in body["due_today"]] == ["Акт приёмки", "Бюджет на квартал"]
        assert body["lock_screen"]["due"]["first"]["title"] == "Акт приёмки"

    async def test_the_lock_screen_is_two_numbers_and_two_rows(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        older = await make_project(
            session, due_on=today() + timedelta(days=100), title="Старый вопрос"
        )
        await ask(session, "project", older.id)
        question = await session.scalar(
            select(LeaderQuestion).where(LeaderQuestion.target_id == older.id)
        )
        assert question is not None
        question.created_at = now_utc() - timedelta(days=4)
        newer = await make_project(session, due_on=today() + timedelta(days=90))
        await ask(session, "project", newer.id)
        await make_task(session, due_at=at_noon(today()), title="Сдать отчёт")
        await session.flush()

        screen = (await leader_api.get(SUMMARY)).json()["lock_screen"]

        assert screen == {
            "awaiting": {
                "count": 2,
                "oldest": {
                    "title": "Старый вопрос",
                    "section": "projects",
                    "decision_kind": None,
                    "context": None,
                    "deviation": 4,
                },
            },
            "due": {
                "count": 1,
                "first": {
                    "title": "Сдать отчёт",
                    "section": "tasks",
                    "decision_kind": None,
                    "context": None,
                    "deviation": 0,
                },
            },
        }

    async def test_an_empty_day_still_has_a_lock_screen(self, leader_api: AsyncClient) -> None:
        """Пустой пункт — `null`, фразу «решений не ждёт» подставляет интерфейс (V29)."""
        body = (await leader_api.get(SUMMARY)).json()

        assert body["lock_screen"] == {"awaiting": None, "due": None}

    async def test_the_time_is_the_threshold(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        body = (await assistant_api.get(SUMMARY)).json()
        # «Повторяет попытку до 11:50» экран берёт отсюда, а не из своей строки.
        assert (body["send_at"], body["last_run"]) == ("08:30", "11:50")
        setting = await session.scalar(select(Setting).where(Setting.key == "summary_at"))
        assert setting is not None
        setting.value = "09:10"
        await session.flush()

        assert (await assistant_api.get(SUMMARY)).json()["send_at"] == "09:10"

    async def test_sent_is_the_delivery_of_today(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """«Пришла в 08:30» — отметка доставки сегодняшней сводки, а не вчерашней."""
        leader = await leader_of(session)
        assert (await assistant_api.get(SUMMARY)).json()["sent_at"] is None
        delivered = datetime(2026, 9, 29, 3, 31, tzinfo=UTC)
        session.add(
            Notification(
                user_id=leader.id,
                kind="morning_summary",
                dedup_key=summary_key(today() - timedelta(days=1), leader.id),
                payload={},
                sent_at=delivered - timedelta(days=1),
            )
        )
        await session.flush()
        assert (await assistant_api.get(SUMMARY)).json()["sent_at"] is None

        session.add(
            Notification(
                user_id=leader.id,
                kind="morning_summary",
                dedup_key=summary_key(today(), leader.id),
                payload={},
                sent_at=delivered,
            )
        )
        await session.flush()

        sent_at = (await assistant_api.get(SUMMARY)).json()["sent_at"]
        assert datetime.fromisoformat(sent_at) == delivered

    async def test_the_device_is_the_latest_the_leader_enabled(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        assert (await assistant_api.get(SUMMARY)).json()["leader_device"] is None
        now = now_utc()
        await subscribe_leader(
            session,
            endpoint="https://fcm.googleapis.com/fcm/send/old-laptop",
            device="Windows",
            created_at=now - timedelta(days=30),
        )
        await subscribe_leader(session, device="iPhone", created_at=now - timedelta(days=8))

        device = (await assistant_api.get(SUMMARY)).json()["leader_device"]

        assert device == {
            "name": "iPhone",
            "since": local_date(now - timedelta(days=8), TASHKENT).isoformat(),
        }

    async def test_without_a_key_there_is_nothing_to_subscribe_to(
        self, leader_api: AsyncClient
    ) -> None:
        """Ключа нет — экран говорит «не настроено», а не предлагает включить."""
        assert (await leader_api.get(SUMMARY)).json()["push_key"] is None

    async def test_with_a_key_the_screen_gets_the_public_one(
        self, leader_api: AsyncClient, push: FakePushSender
    ) -> None:
        assert (await leader_api.get(SUMMARY)).json()["push_key"] == FAKE_PUBLIC_KEY


class TestSubscription:
    async def test_the_leader_enables_notifications_on_his_phone(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        response = await leader_api.put(
            SUBSCRIPTION, json=subscription_body(), headers={"user-agent": IPHONE}
        )

        assert response.status_code == 200
        assert response.json() == {"since": today().isoformat(), "device": "iPhone"}
        stored = await session.scalar(
            select(PushSubscription).where(PushSubscription.endpoint == ENDPOINT)
        )
        assert stored is not None
        assert (stored.p256dh, stored.auth) == (P256DH, AUTH)
        assert stored.user_id == (await leader_of(session)).id

    async def test_the_same_browser_again_updates_and_keeps_since(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Интерфейс сверяет подписку при каждом открытии: строка одна, «с какого дня» —
        день, когда включили, а не последнее открытие."""
        await leader_api.put(SUBSCRIPTION, json=subscription_body())
        stored = await session.scalar(
            select(PushSubscription).where(PushSubscription.endpoint == ENDPOINT)
        )
        assert stored is not None
        enabled = now_utc() - timedelta(days=5)
        stored.created_at = enabled
        await session.flush()
        new_auth = b64url(bytes(range(16, 32)))

        response = await leader_api.put(
            SUBSCRIPTION, json=subscription_body(auth=new_auth), headers={"user-agent": IPHONE}
        )

        assert response.json() == {
            "since": local_date(enabled, TASHKENT).isoformat(),
            "device": "iPhone",
        }
        rows = list(await session.scalars(select(PushSubscription)))
        assert len(rows) == 1
        await session.refresh(rows[0])
        assert rows[0].auth == new_auth

    async def test_the_assistant_does_not_subscribe(self, assistant_api: AsyncClient) -> None:
        """V28: сводку и пуши получает руководитель."""
        response = await assistant_api.put(SUBSCRIPTION, json=subscription_body())

        assert response.status_code == 403
        assert "руководитель" in response.json()["detail"]

    @pytest.mark.parametrize(
        "body",
        [
            subscription_body("https://evil.example/push"),
            subscription_body("http://fcm.googleapis.com/fcm/send/abc"),
            subscription_body(p256dh=b64url(b"\x04" + bytes(10))),
            subscription_body(auth="не-ключ"),
            # Раньше — 500: разбор адреса падал исключением, которого никто не ждал.
            subscription_body("https://[::1].fcm.googleapis.com/"),
            # Раньше — принимались, а утром httpx отказывался по ним отправлять.
            subscription_body("https://a­.fcm.googleapis.com/fcm/send/abc"),
            subscription_body("https://fcm.googleapis.com:abc/fcm/send/abc"),
        ],
    )
    async def test_what_is_not_a_subscription_is_refused(
        self, leader_api: AsyncClient, body: dict[str, object]
    ) -> None:
        response = await leader_api.put(SUBSCRIPTION, json=body)

        assert response.status_code == 422

    async def test_a_subscription_the_service_dropped_is_not_taken_back(
        self,
        leader_api: AsyncClient,
        assistant_api: AsyncClient,
        push: FakePushSender,
        session: AsyncSession,
    ) -> None:
        """Служба ответила 410 — браузер об этом не знает и присылает ту же подписку при
        каждом открытии вкладки. Сервер отвечает 410, а не «Включены»: браузер отписывается,
        и кнопка «Включить уведомления» заводит новый адрес."""
        assert (await leader_api.put(SUBSCRIPTION, json=subscription_body())).status_code == 200
        project = await make_project(session, due_on=today() + timedelta(days=60))
        push.outcomes[ENDPOINT] = PushOutcome.GONE
        asked = await assistant_api.post(
            "/api/v1/questions",
            json={"target_type": "project", "target_id": str(project.id), "text": "Продлить?"},
        )
        assert asked.status_code == 201

        again = await leader_api.put(SUBSCRIPTION, json=subscription_body())

        assert again.status_code == 410
        assert again.json()["type"] == "/problems/gone"
        assert "заново" in again.json()["detail"]
        stored = await session.scalar(
            select(PushSubscription).where(PushSubscription.endpoint == ENDPOINT)
        )
        assert stored is not None
        await session.refresh(stored)
        assert stored.gone_at is not None, "отключённая подписка ожила"
        assert (await assistant_api.get(SUMMARY)).json()["leader_device"] is None

    async def test_a_new_address_after_the_old_one_is_gone_is_accepted(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        dropped = await subscribe_leader(session)
        dropped.gone_at = now_utc()
        await session.flush()
        fresh = "https://web.push.apple.com/a-fresh-address"

        response = await leader_api.put(SUBSCRIPTION, json=subscription_body(fresh))

        assert response.status_code == 200
        assert (await leader_api.get(SUMMARY)).json()["leader_device"]["name"] == "устройство"


class TestQuestionPush:
    """V27: «ждёт вашего решения» — сразу после того, как вопрос записан."""

    @staticmethod
    async def ask_about(assistant_api: AsyncClient, project_id: object) -> str:
        response = await assistant_api.post(
            "/api/v1/questions",
            json={"target_type": "project", "target_id": str(project_id), "text": "Продлить?"},
        )
        assert response.status_code == 201
        question_id: str = response.json()["id"]
        return question_id

    @staticmethod
    async def notification(session: AsyncSession, question_id: str) -> Notification | None:
        found: Notification | None = await session.scalar(
            select(Notification).where(Notification.dedup_key == f"question:{question_id}")
        )
        return found

    async def test_the_leader_gets_it_once_the_question_is_recorded(
        self, assistant_api: AsyncClient, push: FakePushSender, session: AsyncSession
    ) -> None:
        project = await make_project(
            session, due_on=today() + timedelta(days=60), title="Спутник связи"
        )
        await subscribe_leader(session)

        question_id = await self.ask_about(assistant_api, project.id)

        [sent] = push.sent
        assert sent.target.endpoint == ENDPOINT
        assert (sent.ttl, sent.urgency) == (86400, "high")
        assert sent.payload == {
            "kind": "question",
            "tag": f"question:{question_id}",
            "url": "/?view=summary",
            "title": "Спутник связи",
            "question": "Продлить?",
        }
        notification = await self.notification(session, question_id)
        assert notification is not None
        assert notification.sent_at is not None
        assert (notification.kind, notification.entity_type) == ("awaiting_decision", "question")
        assert str(notification.entity_id) == question_id
        assert notification.user_id == (await leader_of(session)).id

    async def test_without_a_device_it_is_recorded_and_not_sent(
        self, assistant_api: AsyncClient, push: FakePushSender, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=today() + timedelta(days=60))

        question_id = await self.ask_about(assistant_api, project.id)

        assert push.sent == []
        notification = await self.notification(session, question_id)
        assert notification is not None
        assert notification.sent_at is None

    async def test_undo_takes_the_unsent_notification_with_it(
        self, assistant_api: AsyncClient, push: FakePushSender, session: AsyncSession
    ) -> None:
        project = await make_project(session, due_on=today() + timedelta(days=60))
        question_id = await self.ask_about(assistant_api, project.id)

        undone = await assistant_api.delete(f"/api/v1/questions/{question_id}")

        assert undone.status_code == 204
        assert await self.notification(session, question_id) is None

    async def test_a_push_already_sent_stays_on_record(
        self, assistant_api: AsyncClient, push: FakePushSender, session: AsyncSession
    ) -> None:
        """Пришедший пуш с телефона не отозвать — и след отправки остаётся (ADR-0036)."""
        project = await make_project(session, due_on=today() + timedelta(days=60))
        await subscribe_leader(session)
        question_id = await self.ask_about(assistant_api, project.id)

        await assistant_api.delete(f"/api/v1/questions/{question_id}")

        notification = await self.notification(session, question_id)
        assert notification is not None
        assert notification.sent_at is not None

    async def test_a_failed_push_does_not_undo_the_question(
        self, assistant_api: AsyncClient, push: FakePushSender, session: AsyncSession
    ) -> None:
        """Служба уведомлений упала — вопрос записан, помощник видит «спросил»."""
        project = await make_project(session, due_on=today() + timedelta(days=60))
        await subscribe_leader(session)
        push.error = RuntimeError("служба уведомлений недоступна")

        question_id = await self.ask_about(assistant_api, project.id)

        assert await session.get(LeaderQuestion, uuid.UUID(question_id)) is not None
        notification = await self.notification(session, question_id)
        assert notification is not None
        assert notification.sent_at is None
