"""Подделки портов для тестов.

Порт подменяется целиком, а не заглушается внутри сценария: сценарий, который в тестах
идёт другой дорогой, чем в бою, проверяет не себя.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.push import PushOutcome, PushTarget

FAKE_PUBLIC_KEY = "BFakePublicKeyForTestsOnly"


@dataclass(frozen=True, slots=True)
class SentPush:
    target: PushTarget
    payload: dict[str, Any]
    ttl: int
    urgency: str


class FakePushSender:
    """Отправитель, который ничего не отправляет, а записывает.

    Исход задаётся по адресу подписки: так один тест проверяет «на один телефон дошло, на
    другой — подписки больше нет». Без явного исхода — `delivered`.
    """

    def __init__(
        self,
        *,
        public_key: str | None = FAKE_PUBLIC_KEY,
        outcomes: dict[str, PushOutcome] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.public_key = public_key
        self.outcomes = outcomes or {}
        self.error = error
        self.sent: list[SentPush] = []

    async def send(
        self, target: PushTarget, payload: dict[str, Any], *, ttl: int, urgency: str
    ) -> PushOutcome:
        if self.error is not None:
            raise self.error
        self.sent.append(SentPush(target=target, payload=payload, ttl=ttl, urgency=urgency))
        return self.outcomes.get(target.endpoint, PushOutcome.DELIVERED)
