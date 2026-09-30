"""Отправка Web Push: что уходит в службу уведомлений и как читаются её ответы.

Служба подменена транспортом httpx, а браузер — парой ключей, созданной здесь же: тест
расшифровывает то, что ушло, ключом «телефона» и проверяет подпись сервера его открытым
ключом. Так проверяется не «вызвали библиотеку», а «телефон это прочтёт и примет».
"""

from __future__ import annotations

import base64
import io
import json
import logging
import time
import uuid
from typing import Any

import http_ece
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid02
from py_vapid.jwt import decode as decode_jwt
from pydantic import SecretStr

from app.adapters.push import (
    DisabledPushSender,
    PushOutcome,
    PushTarget,
    WebPushSender,
    push_sender,
    subject_for,
)
from app.observability import configure_logging
from app.push_keys import new_private_key, private_key_from, public_key_of
from tests.conftest import build_settings

ENDPOINT = "https://fcm.googleapis.com/fcm/send/phone-of-the-leader"
PAYLOAD: dict[str, Any] = {
    "kind": "question",
    "tag": "question:1",
    "url": "/?view=summary",
    "title": "Спутник",
    "question": "Продлить срок испытаний?",
}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class Phone:
    """Браузер руководителя: пара ключей и секрет подписки."""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = bytes(range(16))

    @property
    def target(self) -> PushTarget:
        public = self.key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        return PushTarget(endpoint=ENDPOINT, p256dh=b64url(public), auth=b64url(self.auth))

    def read(self, body: bytes) -> dict[str, Any]:
        plain = http_ece.decrypt(
            body, private_key=self.key, auth_secret=self.auth, version="aes128gcm"
        )
        result: dict[str, Any] = json.loads(plain)
        return result


class Service:
    """Служба уведомлений: запоминает запрос и отвечает заданным кодом."""

    def __init__(self, status: int = 201, error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return httpx.Response(self.status, text="причина отказа")


def sender_for(service: Service, subject: str = "mailto:noreply@orbita.local") -> WebPushSender:
    return WebPushSender(new_private_key(), subject, transport=httpx.MockTransport(service))


class TestWhatLeavesTheServer:
    async def test_the_phone_reads_what_was_sent(self) -> None:
        phone, service = Phone(), Service()

        outcome = await sender_for(service).send(phone.target, PAYLOAD, ttl=86400, urgency="high")

        assert outcome is PushOutcome.DELIVERED
        [request] = service.requests
        assert str(request.url) == ENDPOINT
        assert phone.read(request.content) == PAYLOAD

    async def test_the_headers_say_how_long_and_how_urgent(self) -> None:
        service = Service()

        await sender_for(service).send(Phone().target, PAYLOAD, ttl=43200, urgency="normal")

        headers = service.requests[0].headers
        assert headers["TTL"] == "43200"
        assert headers["Urgency"] == "normal"
        assert headers["Content-Encoding"] == "aes128gcm"

    async def test_the_service_can_verify_the_server(self) -> None:
        """Подпись VAPID сверяется открытым ключом из того же заголовка — тем, что отдан
        браузеру для подписки. Разойдутся — служба откажет каждому пушу."""
        service = Service()
        sender = sender_for(service, subject="https://orbita.example.uz")

        await sender.send(Phone().target, PAYLOAD, ttl=60, urgency="high")

        authorization = service.requests[0].headers["Authorization"]
        scheme, _, params = authorization.partition(" ")
        parts = dict(part.strip().split("=", 1) for part in params.split(","))
        assert scheme == "vapid"
        assert parts["k"] == sender.public_key
        assert Vapid02.verify(authorization) is True
        claims = decode_jwt(parts["t"], parts["k"])
        assert claims["aud"] == "https://fcm.googleapis.com"
        assert claims["sub"] == "https://orbita.example.uz"
        assert time.time() < claims["exp"] <= time.time() + 24 * 3600


class TestWhatTheServiceAnswered:
    @pytest.mark.parametrize(
        ("status", "outcome"),
        [
            (201, PushOutcome.DELIVERED),
            (202, PushOutcome.DELIVERED),
            (404, PushOutcome.GONE),
            (410, PushOutcome.GONE),
            (400, PushOutcome.FAILED),
            (403, PushOutcome.FAILED),
            (413, PushOutcome.FAILED),
            (429, PushOutcome.FAILED),
            (500, PushOutcome.FAILED),
        ],
    )
    async def test_status_becomes_an_outcome(self, status: int, outcome: PushOutcome) -> None:
        sent = await sender_for(Service(status)).send(
            Phone().target, PAYLOAD, ttl=60, urgency="high"
        )

        assert sent is outcome

    @pytest.mark.parametrize(
        "error",
        [httpx.ReadTimeout("не ответила"), httpx.ConnectError("нет сети")],
    )
    async def test_silence_and_network_are_failures(self, error: Exception) -> None:
        sent = await sender_for(Service(error=error)).send(
            Phone().target, PAYLOAD, ttl=60, urgency="high"
        )

        assert sent is PushOutcome.FAILED

    async def test_a_broken_stored_key_fails_without_a_request(self) -> None:
        service = Service()
        broken = PushTarget(endpoint=ENDPOINT, p256dh=b64url(b"\x04" + bytes(64)), auth="AAAA")

        sent = await sender_for(service).send(broken, PAYLOAD, ttl=60, urgency="high")

        assert sent is PushOutcome.FAILED
        assert service.requests == []

    @pytest.mark.parametrize(
        "endpoint",
        [
            "https://a\u00ad.fcm.googleapis.com/fcm/send/abc",
            "https://fcm.googleapis.com:abc/fcm/send/abc",
            "https://[::1].fcm.googleapis.com/",
            "https://xn--zz.fcm.googleapis.com/fcm/send/abc",
        ],
    )
    async def test_an_address_httpx_cannot_send_to_is_a_failure(self, endpoint: str) -> None:
        """Отправка не бросает исключений: одна плохая подписка не обрывает рассылку
        остальным. `httpx.InvalidURL` — не наследник `httpx.HTTPError`, и без явной
        обработки вылетал бы наружу."""
        service = Service()
        phone = Phone().target
        target = PushTarget(endpoint=endpoint, p256dh=phone.p256dh, auth=phone.auth)

        sent = await sender_for(service).send(target, PAYLOAD, ttl=60, urgency="high")

        assert sent is PushOutcome.FAILED
        assert service.requests == []

    @pytest.mark.parametrize(
        "error",
        [
            OverflowError("connect(): port must be 0-65535."),
            ExceptionGroup("connect", [OverflowError("connect(): port must be 0-65535.")]),
        ],
    )
    async def test_an_unexpected_error_on_the_way_is_a_failure(self, error: Exception) -> None:
        """Так ведёт себя порт вне 0–65535 на Linux: не `httpx.HTTPError`, а группа с
        `OverflowError`. Отправка всё равно отвечает «не доставлено», а не бросает."""

        def refuse(request: httpx.Request) -> httpx.Response:
            raise error

        sender = WebPushSender(
            new_private_key(), "mailto:noreply@orbita.local", transport=httpx.MockTransport(refuse)
        )

        sent = await sender.send(Phone().target, PAYLOAD, ttl=60, urgency="high")

        assert sent is PushOutcome.FAILED

    async def test_what_does_not_fit_is_not_sent(self) -> None:
        """Служба не примет больше 4 КБ — и две записи вместо одной тоже не примет."""
        service = Service()

        sent = await sender_for(service).send(
            Phone().target, {"question": "Я" * 3000}, ttl=60, urgency="high"
        )

        assert sent is PushOutcome.FAILED
        assert service.requests == []


class TestLog:
    async def test_the_address_of_the_subscription_stays_out_of_the_log(self) -> None:
        """Адрес подписки — право отправить пуш на телефон руководителя. httpx пишет
        каждый запрос с полным адресом на уровне INFO, и приложение его приглушает."""
        token = f"device-token-{uuid.uuid4().hex}"
        phone = Phone().target
        target = PushTarget(
            endpoint=f"https://web.push.apple.com/{token}", p256dh=phone.p256dh, auth=phone.auth
        )
        configure_logging(level="INFO", json_output=True)
        stream = io.StringIO()
        handler = logging.getLogger().handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        handler.setStream(stream)

        sent = await sender_for(Service()).send(target, PAYLOAD, ttl=60, urgency="high")
        logging.getLogger("проверка").info("запись после отправки")

        assert sent is PushOutcome.DELIVERED
        assert "запись после отправки" in stream.getvalue(), "поток журнала не подменился"
        assert token not in stream.getvalue()


class TestConfiguration:
    def test_the_public_key_comes_from_the_private_one(self) -> None:
        secret = new_private_key()
        public = public_key_of(private_key_from(secret))

        assert len(base64.urlsafe_b64decode(public + "=")) == 65
        assert WebPushSender(secret, "mailto:noreply@orbita.local").public_key == public

    def test_without_a_key_push_is_off(self) -> None:
        sender = push_sender(build_settings())

        assert isinstance(sender, DisabledPushSender)
        assert sender.public_key is None

    async def test_the_disabled_sender_sends_nothing(self) -> None:
        sent = await DisabledPushSender().send(Phone().target, PAYLOAD, ttl=60, urgency="high")

        assert sent is PushOutcome.FAILED

    def test_with_a_key_push_is_on(self) -> None:
        secret = new_private_key()
        settings = build_settings().model_copy(update={"vapid_private_key": SecretStr(secret)})

        sender = push_sender(settings)

        assert isinstance(sender, WebPushSender)
        assert sender.public_key == public_key_of(private_key_from(secret))

    @pytest.mark.parametrize(
        ("base_url", "subject"),
        [
            ("https://orbita.netlify.app", "https://orbita.netlify.app"),
            ("https://orbita.netlify.app/", "https://orbita.netlify.app"),
            ("https://host.example:8443/path", "https://host.example"),
            ("http://localhost:5173", "mailto:noreply@orbita.local"),
        ],
    )
    def test_the_contact_is_the_system_address_when_it_is_https(
        self, base_url: str, subject: str
    ) -> None:
        assert subject_for(base_url) == subject


def test_the_key_command_prints_one_line_for_the_environment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Строку дописывают в $GITHUB_ENV как есть: лишняя строка вывода сломала бы прогон."""
    from app import push_keys

    assert push_keys.main() == 0

    out = capsys.readouterr().out
    name, _, value = out.removesuffix("\n").partition("=")
    assert out.count("\n") == 1
    assert name == "ORBITA_VAPID_PRIVATE_KEY"
    assert len(value) == 43
    private_key_from(value)
