"""Ключ сервера для уведомлений: формат и команда `uv run python -m app.push_keys`.

Команда печатает ровно одну строку `ORBITA_VAPID_PRIVATE_KEY=<ключ>` — в том виде, в каком
её кладут в окружение. Отсюда два применения, и оба без правки вывода руками:

- заказчик вставляет значение в переменные окружения Vercel (docs/SETUP.md);
- проверки CI дописывают строку в `$GITHUB_ENV` и получают одноразовый ключ на прогон —
  ключа в репозитории нет (инвариант 12).

Формат ключа знает только этот модуль: его читают настройки на старте
(`app.settings.Settings`) и отправитель (`app.adapters.push`). Вне слоёв, как и
`app.access_cli`: настройки нужны слою данных, и адаптер, импортированный настройками,
тянул бы слой адаптеров в слой данных.

Открытый ключ не печатается: сервер выводит его из закрытого и отдаёт экрану сам
(`GET /api/v1/pult/summary`, поле `push_key`). **Смена ключа отключает подписки**: браузер
подписан на конкретный открытый ключ, и после замены руководитель включает уведомления
заново.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.domain.errors import RuleViolationError
from app.domain.push import decode_key

PRIVATE_KEY_BYTES = 32


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def private_key_from(value: str) -> ec.EllipticCurvePrivateKey:
    """Закрытый ключ из `ORBITA_VAPID_PRIVATE_KEY`. Не ключ — `ValueError`."""
    try:
        raw = decode_key(value.strip())
    except RuleViolationError as error:
        raise ValueError("ключ не в base64url") from error
    if len(raw) != PRIVATE_KEY_BYTES:
        raise ValueError("ключ P-256 — ровно 32 байта")
    # Ноль и числа не меньше порядка кривой ключом не являются — здесь это ValueError.
    return ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())


def public_key_of(key: ec.EllipticCurvePrivateKey) -> str:
    """Открытый ключ для `pushManager.subscribe` — base64url несжатой точки P-256."""
    return _b64url(key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))


def new_private_key() -> str:
    """Свежий закрытый ключ в том виде, в каком его кладут в окружение."""
    key = ec.generate_private_key(ec.SECP256R1())
    return _b64url(key.private_numbers().private_value.to_bytes(PRIVATE_KEY_BYTES, "big"))


def main() -> int:
    print(f"ORBITA_VAPID_PRIVATE_KEY={new_private_key()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
