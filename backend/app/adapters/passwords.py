"""Хеширование паролей.

Argon2id — параметры по умолчанию из библиотеки, они соответствуют текущим рекомендациям
OWASP и меняются вместе с ней. Подбирать их вручную здесь не нужно: чужие цифры из статьи
пятилетней давности хуже, чем сопровождаемые значения.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Минимальная длина без требований к составу символов.
# Требования вида «заглавная, цифра и знак» дают предсказуемые пароли вида Parol2026! —
# длина даёт больше, чем обязательный набор символов.
MIN_PASSWORD_LENGTH = 12

_hasher = PasswordHasher()

# Хеш заведомо недостижимого пароля. Нужен, чтобы проверка несуществующего пользователя
# занимала столько же времени, сколько проверка существующего: иначе по времени ответа
# перебором определяется, какие адреса заведены в системе.
_DUMMY_HASH = _hasher.hash("несуществующий-пароль-для-выравнивания-времени")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Проверяет пароль. Отсутствие хеша обрабатывается за то же время, что и наличие."""
    try:
        _hasher.verify(password_hash if password_hash else _DUMMY_HASH, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    return bool(password_hash)


def needs_rehash(password_hash: str) -> bool:
    """Параметры библиотеки со временем ужесточаются — старый хеш стоит пересчитать."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
