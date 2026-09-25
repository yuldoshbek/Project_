"""Доступ по личной ссылке.

Входа в систему нет: у каждого из двух пользователей своя секретная ссылка, переход по
которой ставит cookie сессии на тридцать дней
([ADR-0029](../../../docs/adr/ADR-0029-access-by-link.md)).

Здесь только правила, без базы и без HTTP: как выглядит токен, как из токена получается
отпечаток и когда сессия считается годной.

**Почему отпечаток, а не токен.** В базе лежит HMAC-SHA256 от токена на ключе приложения.
Три последствия, каждое из которых оплачено практикой:

1. Копия базы не даёт войти: без ключа отпечаток не превратить в ссылку.
2. Сравнение идёт по отпечатку фиксированной длины, а не по секрету переменной.
3. В журналах и отчётах об ошибках токен не появляется никогда — печатать нечего.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

SESSION_COOKIE = "__Host-orbita"
"""Имя cookie сессии.

Префикс `__Host-` — не украшение: браузер принимает такую cookie только с `Secure`, только
с `Path=/` и только без `Domain`, то есть её нельзя выставить с соседнего поддомена. Для
системы, у которой вход — это ссылка, подмена cookie была бы подменой пользователя.
"""

TOKEN_BYTES = 32
"""Длина случайной части токена. 32 байта — 256 бит: перебор невозможен, а ссылка ещё
влезает в одно сообщение."""

# Отпечаток последнего входа обновляется не на каждом запросе: при опросе раз в пятнадцать
# секунд (ADR-0034) это была бы запись в базу четыре раза в минуту на пустом месте.
TOUCH_INTERVAL = timedelta(minutes=30)


VISIT_GAP = timedelta(hours=2)
"""Перерыв, после которого обращение считается новым визитом.

От конца прошлого визита считается «что изменилось с моего прошлого визита» (Пульт).
Два часа, а не «новая сессия»: сессия живёт тридцать дней, и руководитель открывает
систему утром, в обед и вечером — это три визита, а не один. Меньше двух часов — это
та же работа, прерванная совещанием.
"""


def visit_began(last_seen_at: datetime | None, now: datetime) -> bool:
    """Начался ли новый визит: с последнего обращения прошло больше `VISIT_GAP`."""
    return last_seen_at is not None and now - last_seen_at >= VISIT_GAP


def new_token() -> str:
    """Новый секрет для ссылки или сессии."""
    return secrets.token_urlsafe(TOKEN_BYTES)


MIN_GIVEN_TOKEN_LENGTH = 43
"""Длина `token_urlsafe(32)`: заданный извне токен не слабее того, что выпускает система."""

_URL_SAFE = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def is_acceptable_given_token(token: str) -> bool:
    """Годится ли токен, заданный человеком, а не системой.

    Нужен первой ссылке в облаке: её токен заказчик кладёт в секрет GitHub, и ссылку
    собирает сам — иначе её пришлось бы печатать в журнал прогона публичного репозитория.
    Правило то же, что у выпускаемых: не короче и только символы, которые не меняются в
    адресе.
    """
    return len(token) >= MIN_GIVEN_TOKEN_LENGTH and set(token) <= _URL_SAFE


def fingerprint(token: str, secret: str) -> str:
    """Отпечаток токена. Только он попадает в базу."""
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def same_fingerprint(left: str, right: str) -> bool:
    """Сравнение отпечатков за постоянное время.

    Обычное `==` на строках выходит из сравнения на первом несовпавшем символе, и по
    времени ответа отпечаток подбирается посимвольно. Здесь сравниваются значения
    одинаковой длины, так что утечки длины тоже нет.
    """
    return hmac.compare_digest(left, right)


def link_for(base_url: str, token: str) -> str:
    """Ссылка, которую отправляют человеку.

    Путь начинается с `/api`, потому что интерфейс проксирует на API только его
    (ADR-0028): ссылка вида `/a/<токен>` вернула бы страницу приложения, а не сессию.
    """
    return f"{base_url.rstrip('/')}/api/access/{token}"


@dataclass(frozen=True, slots=True)
class SessionWindow:
    """Срок сессии: когда открыта и когда истекает."""

    opened_at: datetime
    expires_at: datetime

    @classmethod
    def opened(cls, now: datetime, days: int) -> SessionWindow:
        return cls(opened_at=now, expires_at=now + timedelta(days=days))


def is_alive(expires_at: datetime, revoked_at: datetime | None, now: datetime) -> bool:
    """Годна ли сессия.

    Отозванная сессия мертва сразу, не дожидаясь срока: перевыпуск ссылки должен
    закрывать доступ в тот же момент, иначе он не защищает от пересылки ссылки.
    """
    if revoked_at is not None:
        return False
    return expires_at > now


def needs_touch(last_seen_at: datetime | None, now: datetime) -> bool:
    """Пора ли обновить отметку последнего обращения."""
    if last_seen_at is None:
        return True
    return now - last_seen_at >= TOUCH_INTERVAL
