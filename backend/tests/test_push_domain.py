"""Правила уведомлений без базы и сети: подписка, устройство, содержимое, время сводки."""

from __future__ import annotations

import base64
import uuid
from datetime import date, time

import pytest

from app.adapters.push import MAX_PLAINTEXT, plaintext
from app.domain.attention import Attention
from app.domain.decisions import TEXT_MAX_LENGTH as DECISION_MAX_LENGTH
from app.domain.errors import PermissionDeniedError, RuleViolationError
from app.domain.management import clean_threshold, threshold_bounds
from app.domain.people import Role
from app.domain.push import (
    PUSH_FIELD_LENGTH,
    QUESTION_PREVIEW_LENGTH,
    NotificationKind,
    SummaryOutcome,
    check_subscriber,
    clean_subscription,
    device_name,
    preview,
    question_key,
    question_payload,
    summary_blocker,
    summary_due,
    summary_key,
    summary_payload,
)
from app.services.pult import RowView
from app.services.summary import lock_screen, lock_screen_payload


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


P256DH = b64url(b"\x04" + bytes(range(64)))
AUTH = b64url(bytes(range(16)))
FCM = "https://fcm.googleapis.com/fcm/send/abc:def"


class TestDeviceName:
    @pytest.mark.parametrize(
        ("user_agent", "name"),
        [
            (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
                "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
                "iPhone",
            ),
            ("Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15", "iPad"),
            ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/128", "Android"),
            ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15", "Mac"),
            ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/128", "Windows"),
            ("Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0", "Linux"),
            ("pytest", "устройство"),
            (None, "устройство"),
            ("", "устройство"),
        ],
    )
    def test_named_by_the_browser_header(self, user_agent: str | None, name: str) -> None:
        assert device_name(user_agent) == name


class TestSubscription:
    def test_a_real_subscription_is_accepted(self) -> None:
        cleaned = clean_subscription(endpoint=f" {FCM} ", p256dh=P256DH, auth=AUTH)

        assert (cleaned.endpoint, cleaned.p256dh, cleaned.auth) == (FCM, P256DH, AUTH)

    @pytest.mark.parametrize(
        "endpoint",
        [
            "https://web.push.apple.com/QGuQyavXu",
            "https://fcm.googleapis.com/wp/abc",
            "https://updates.push.services.mozilla.com/wpush/v2/abc",
            "https://wns2-par02p.notify.windows.com/w/?token=abc",
        ],
    )
    def test_every_browser_service_is_known(self, endpoint: str) -> None:
        assert clean_subscription(endpoint=endpoint, p256dh=P256DH, auth=AUTH).endpoint == endpoint

    @pytest.mark.parametrize(
        "endpoint",
        [
            "http://fcm.googleapis.com/fcm/send/abc",
            "https://evil.example/fcm/send/abc",
            "https://fcm.googleapis.com.evil.example/abc",
            "https://notfcm.googleapis.com.example/abc",
            "https://fcm.googleapis.com@169.254.169.254/latest",
            "https://127.0.0.1/abc",
            "https://fcm.googleapis.com/" + "a" * 1000,
            "https://fcm.googleapis.com/a b",
            "fcm.googleapis.com/abc",
            # Адреса, которые httpx не отправит: мягкий перенос в имени, скобки, порт из букв.
            "https://a\u00ad.fcm.googleapis.com/abc",
            "https://[::1].fcm.googleapis.com/",
            "https://fcm.googleapis.com]/abc",
            "https://fcm.googleapis.com:abc/x",
            # Испорченный punycode и порт: `httpx.URL` их не проверяет, пока не спросят.
            "https://xn--zz.fcm.googleapis.com/x",
            "https://fcm.googleapis.com:99999/x",
            "https://fcm.googleapis.com:-1/x",
            "https://fcm.googleapis.com:8443/x",
        ],
    )
    def test_the_server_does_not_post_anywhere_else(self, endpoint: str) -> None:
        """Сервер сам отправляет POST по адресу подписки — чужой адрес не принимается."""
        with pytest.raises(RuleViolationError):
            clean_subscription(endpoint=endpoint, p256dh=P256DH, auth=AUTH)

    @pytest.mark.parametrize(
        ("p256dh", "auth"),
        [
            (b64url(b"\x04" + bytes(63)), AUTH),
            (b64url(b"\x02" + bytes(64)), AUTH),
            (P256DH, b64url(bytes(15))),
            (P256DH + "!", AUTH),
            ("", AUTH),
            (P256DH, "кириллица"),
        ],
    )
    def test_broken_keys_are_refused(self, p256dh: str, auth: str) -> None:
        with pytest.raises(RuleViolationError) as error:
            clean_subscription(endpoint=FCM, p256dh=p256dh, auth=auth)

        assert "включите уведомления заново" in error.value.message

    def test_padded_keys_are_accepted_too(self) -> None:
        padded = base64.urlsafe_b64encode(b"\x04" + bytes(64)).decode("ascii")

        assert clean_subscription(endpoint=FCM, p256dh=padded, auth=AUTH).p256dh == padded

    def test_only_the_leader_subscribes(self) -> None:
        """V28: сводку и пуши получает руководитель."""
        check_subscriber(Role.LEADER)
        with pytest.raises(PermissionDeniedError) as error:
            check_subscriber(Role.ASSISTANT)

        assert "руководитель" in error.value.message


class TestPayload:
    def test_the_summary_carries_data_not_words(self) -> None:
        screen = {"awaiting": {"count": 2, "oldest": {"title": "Миссия"}}, "due": None}

        payload = summary_payload(date(2026, 9, 29), screen)

        assert payload == {
            "kind": "summary",
            "tag": "morning-summary:2026-09-29",
            "url": "/?view=summary",
            "lock_screen": screen,
        }

    def test_the_question_names_its_target(self) -> None:
        question = uuid.uuid4()

        payload = question_payload(question, title="Спутник", text="Продлить срок?")

        assert payload == {
            "kind": "question",
            "tag": f"question:{question}",
            "url": "/?view=summary",
            "title": "Спутник",
            "question": "Продлить срок?",
        }

    def test_a_long_question_is_cut_to_fit_the_push(self) -> None:
        """Служба принимает 4 КБ: тысяча кириллических символов вопроса — уже половина."""
        payload = question_payload(uuid.uuid4(), title="Н" * 300, text="Я" * 1000)

        assert len(payload["question"]) == QUESTION_PREVIEW_LENGTH
        assert payload["question"].endswith("…")
        assert len(payload["title"]) == PUSH_FIELD_LENGTH

    def test_the_longest_question_fits_the_push(self) -> None:
        payload = question_payload(
            uuid.uuid4(), title="Н" * DECISION_MAX_LENGTH, text="Я" * DECISION_MAX_LENGTH
        )

        assert len(plaintext(payload)) <= MAX_PLAINTEXT

    def test_the_longest_summary_fits_the_push(self) -> None:
        """Решение в тысячу кириллических символов с подписью в тысячу — так сводка не
        проходила бы ни разу, пока эта строка стоит первой. Предел держит домен."""
        row = RowView(
            section="decisions",
            entity_id=uuid.uuid4(),
            title="Я" * DECISION_MAX_LENGTH,
            decision_kind="approve",
            context="Ж" * DECISION_MAX_LENGTH,
            step=Attention.AWAITING_DECISION,
            deviation=-99999,
            due_on=None,
            original_due_on=None,
            responsible=None,
            question=None,
            last_decision=None,
            target_type="project",
            target_id=uuid.uuid4(),
        )
        screen = lock_screen([row] * 999, [row] * 999)

        payload = summary_payload(date(2026, 9, 29), lock_screen_payload(screen))

        assert len(plaintext(payload)) <= MAX_PLAINTEXT
        assert screen.awaiting is not None
        assert len(screen.awaiting.oldest.title or "") == PUSH_FIELD_LENGTH
        assert len(screen.awaiting.oldest.context or "") == PUSH_FIELD_LENGTH

    def test_preview_cuts_with_an_ellipsis(self) -> None:
        assert preview("коротко", 10) == "коротко"
        assert preview("ровно десять", 12) == "ровно десять"
        assert preview("слово за словом", 10) == "слово за…"

    def test_dedup_keys_are_deterministic(self) -> None:
        user = uuid.UUID(int=7)
        question = uuid.UUID(int=9)

        assert summary_key(date(2026, 9, 29), user) == f"morning-summary:2026-09-29:{user}"
        assert question_key(question) == f"question:{question}"

    def test_the_question_wakes_the_phone_and_the_summary_may_wait(self) -> None:
        assert NotificationKind.AWAITING_DECISION.urgency == "high"
        assert NotificationKind.MORNING_SUMMARY.urgency == "normal"
        assert NotificationKind.MORNING_SUMMARY.ttl == 43200
        assert NotificationKind.AWAITING_DECISION.ttl == 86400


class TestSummaryTime:
    def test_due_from_the_set_minute_on(self) -> None:
        """Не «ровно в 08:30»: расписание может прийти в 08:40, и тогда пора тоже."""
        assert summary_due(time(8, 29), "08:30") is False
        assert summary_due(time(8, 30), "08:30") is True
        assert summary_due(time(8, 40), "08:30") is True

    @pytest.mark.parametrize("value", ["05:59", "11:01", "11:50", "20:00", "00:00", "23:59"])
    def test_a_time_the_schedule_cannot_serve_is_refused(self, value: str) -> None:
        """Время вне окна не наступило бы или получило бы одну попытку вместо шести."""
        with pytest.raises(RuleViolationError) as error:
            clean_threshold(value_type="time", value=value, low=None, high=None)

        assert "с 06:00 до 11:00" in error.value.message
        assert "до 11:50" in error.value.message

    @pytest.mark.parametrize("value", ["06:00", "08:30", "11:00"])
    def test_a_time_inside_the_window_is_kept(self, value: str) -> None:
        assert clean_threshold(value_type="time", value=value, low=None, high=None) == value

    def test_the_screen_gets_the_same_window(self) -> None:
        """Экран ставит границы полю времени — те же, что проверяет сервер."""
        assert threshold_bounds(value_type="time", low=None, high=None) == ("06:00", "11:00")
        assert threshold_bounds(value_type="days", low=1, high=60) == (1, 60)

    @pytest.mark.parametrize(
        ("local_now", "configured", "has_device", "blocker"),
        [
            (time(8, 29), True, True, SummaryOutcome.NOT_YET),
            (time(8, 29), False, False, SummaryOutcome.NOT_YET),
            (time(8, 30), False, True, SummaryOutcome.NOT_CONFIGURED),
            (time(8, 30), False, False, SummaryOutcome.NOT_CONFIGURED),
            (time(9, 10), True, False, SummaryOutcome.NO_DEVICE),
            (time(9, 10), True, True, None),
        ],
    )
    def test_what_holds_the_summary_back(
        self,
        local_now: time,
        configured: bool,
        has_device: bool,
        blocker: SummaryOutcome | None,
    ) -> None:
        """«Некому» и «нечем» — не отправка, а ожидание: день остаётся свободным."""
        found = summary_blocker(
            local_now=local_now, send_at="08:30", configured=configured, has_device=has_device
        )

        assert found is blocker
