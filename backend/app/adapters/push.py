"""Порт отправки уведомлений на устройство — Web Push (RFC 8030, 8291, 8292).

**Порт — это обещание, а не библиотека.** Сценарии знают только `PushSender`: «отправь
это содержимое на эту подписку и скажи, чем кончилось». Как именно — шифрование, подпись,
HTTP — знает реализация, и подменяется она конфигом, а не переписыванием сценариев
(CLAUDE.md, ключевые порты): без ключа в окружении работает `DisabledPushSender`, в тестах —
подделка из `tests/fakes.py`, в облаке и на сервере агентства — `WebPushSender`.

Исходов у отправки три, и сценарию важны именно они, а не коды ответа служб:

- `delivered` — служба приняла пуш (201 или 202);
- `gone` — подписки больше нет (404, 410): браузер отписался, приложение удалили; такую
  подписку сценарий отмечает отключённой, иначе каждое утро стучался бы в пустоту;
- `failed` — всё остальное: сеть, тайм-аут, отказ службы, адрес, который не удалось
  разобрать. Это может пройти, и подписка остаётся. Отправка не бросает исключений: одна
  плохая подписка не должна обрывать рассылку остальным.

В журнал не попадают ни адрес подписки, ни ключи: адрес подписки — сам по себе право
отправить пуш на телефон руководителя. Журнал запросов httpx, который пишет адрес целиком,
приглушён там же, где настраиваются логи (`app.observability.QUIET_LOGGERS`).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlsplit

import structlog
from cryptography.hazmat.primitives.asymmetric import ec

from app.domain.errors import RuleViolationError
from app.domain.push import decode_key
from app.push_keys import private_key_from, public_key_of

if TYPE_CHECKING:
    import httpx

    from app.settings import Settings

logger = structlog.get_logger(__name__)

SEND_TIMEOUT = 5.0
"""Секунд на одну отправку. Функция на Vercel живёт не дольше 60 секунд
(`vercel.json`, `maxDuration`), а служба, не ответившая за пять, скорее не ответит вовсе —
лучше честный `failed` и повтор расписания, чем функция, убитая посреди сводки."""

JWT_LIFETIME = 12 * 3600
"""Срок подписи сервера. RFC 8292 разрешает до суток, но службы считают сутки по своим
часам: подпись «ровно на сутки» у Apple и Google иногда отклоняется как слишком долгая."""

MAX_PLAINTEXT = 4096 - 86 - 17
"""Больше содержимого служба не примет: 4096 байт зашифрованного тела минус заголовок
aes128gcm (соль, размер записи, длина и ключ — 86 байт) минус разделитель и метка
шифрования (17). Содержимое, которое не влезает, уходит `failed`, а не двумя записями,
которых служба не поймёт (RFC 8291, раздел 4: запись ровно одна)."""

MAILTO_SUBJECT = "mailto:noreply@orbita.local"
"""Контакт отправителя для службы, когда у системы нет своего адреса https (разработка)."""


def plaintext(payload: dict[str, Any]) -> bytes:
    """Содержимое пуша в байтах — ровно то, что шифруется и уходит в службу."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


class PushOutcome(StrEnum):
    DELIVERED = "delivered"
    GONE = "gone"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PushTarget:
    """Подписка браузера: куда отправлять и чем шифровать."""

    endpoint: str
    p256dh: str
    auth: str


class PushSender(Protocol):
    """Отправитель уведомлений на устройство."""

    public_key: str | None
    """Открытый ключ сервера для `pushManager.subscribe` — base64url несжатой точки P-256.
    `None` — уведомления не настроены, и экран так и говорит."""

    async def send(
        self, target: PushTarget, payload: dict[str, Any], *, ttl: int, urgency: str
    ) -> PushOutcome: ...


def subject_for(base_url: str) -> str:
    """Контакт отправителя в подписи (`sub`, RFC 8292, раздел 2.1).

    Адрес системы, когда он https, — по нему служба найдёт, чей это сервер. Только схема и
    хост: py_vapid принимает `https://хост` и ничего сверх того.
    """
    parts = urlsplit(base_url)
    if parts.scheme == "https" and parts.hostname:
        return f"https://{parts.hostname}"
    return MAILTO_SUBJECT


class DisabledPushSender:
    """Уведомления не настроены: ключа в окружении нет. Отправки нет, отказа — тоже."""

    def __init__(self) -> None:
        self.public_key: str | None = None

    async def send(
        self, target: PushTarget, payload: dict[str, Any], *, ttl: int, urgency: str
    ) -> PushOutcome:
        return PushOutcome.FAILED


class WebPushSender:
    """Отправка через службы уведомлений браузеров.

    Клиент HTTP, шифрование и подпись загружаются при первой отправке, а не при старте:
    отправка бывает раз в сутки и на вопрос помощника, а холодный старт функции платит
    каждый запрос руководителя. Замер 29.09.2026 на машине разработки: httpx, http_ece и
    py_vapid вместе — полсекунды импорта.
    """

    def __init__(
        self,
        private_key: str,
        subject: str,
        *,
        timeout: float = SEND_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._key = private_key_from(private_key)
        self._subject = subject
        self._timeout = timeout
        self._transport = transport
        self.public_key: str | None = public_key_of(self._key)

    async def send(
        self, target: PushTarget, payload: dict[str, Any], *, ttl: int, urgency: str
    ) -> PushOutcome:
        import http_ece
        import httpx
        from py_vapid import Vapid02, VapidException

        try:
            endpoint = urlsplit(target.endpoint)
        except ValueError:
            logger.warning("push_not_prepared", service=None, reason="ValueError")
            return PushOutcome.FAILED
        service = endpoint.hostname
        content = plaintext(payload)
        if len(content) > MAX_PLAINTEXT:
            logger.warning("push_payload_too_large", service=service, size=len(content))
            return PushOutcome.FAILED

        try:
            body = http_ece.encrypt(
                content,
                salt=os.urandom(16),
                # Свой одноразовый ключ на каждую отправку (RFC 8291, раздел 3.1).
                private_key=ec.generate_private_key(ec.SECP256R1()),
                dh=decode_key(target.p256dh),
                auth_secret=decode_key(target.auth),
                version="aes128gcm",
            )
            signed = Vapid02(private_key=self._key).sign(
                {
                    "aud": f"{endpoint.scheme}://{endpoint.netloc}",
                    "exp": int(time.time()) + JWT_LIFETIME,
                    "sub": self._subject,
                }
            )
        except (ValueError, RuleViolationError, http_ece.ECEException, VapidException) as error:
            logger.warning("push_not_prepared", service=service, reason=type(error).__name__)
            return PushOutcome.FAILED

        headers = {
            "TTL": str(ttl),
            "Urgency": urgency,
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "Authorization": signed["Authorization"],
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(target.endpoint, content=body, headers=headers)
        except Exception as error:
            # Намеренно всё, а не перечень: кроме `httpx.HTTPError` на отправке встречаются
            # `InvalidURL`, `IDNAError` (имя хоста разбирается только здесь) и на Linux
            # `OverflowError` в группе исключений от порта вне 0–65535 — проверено на httpx
            # 0.28.1. Любое из них, вылетев наружу, оборвало бы рассылку остальным
            # устройствам и откатило бы отметки уже доставленных.
            logger.warning("push_failed", service=service, reason=type(error).__name__)
            return PushOutcome.FAILED

        if response.status_code in (201, 202):
            return PushOutcome.DELIVERED
        if response.status_code in (404, 410):
            logger.info("push_subscription_gone", service=service, status=response.status_code)
            return PushOutcome.GONE
        # Тело отказа — причина от службы («BadJwtToken», «VapidPkHashMismatch»): без неё
        # 403 после смены ключа неотличим от 403 из-за часов.
        logger.warning(
            "push_refused",
            service=service,
            status=response.status_code,
            reason=response.text[:200],
        )
        return PushOutcome.FAILED


def push_sender(settings: Settings) -> PushSender:
    """Отправитель по конфигу: есть ключ — настоящий, нет — выключенный."""
    if settings.vapid_private_key is None:
        return DisabledPushSender()
    return WebPushSender(
        settings.vapid_private_key.get_secret_value(), subject_for(settings.base_url)
    )
