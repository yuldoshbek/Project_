"""Вход, обновление сессии, выход, смена пароля.

Здесь собраны правила, которые нельзя оставлять на усмотрение роутера: отказ выглядит
одинаково независимо от причины, перебор упирается в блокировку, а токен обновления
одноразовый.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.identity import Credentials, IdentityProvider
from app.adapters.passwords import MIN_PASSWORD_LENGTH, hash_password, verify_password
from app.domain.errors import NotAuthenticatedError, PermissionDeniedError, RuleViolationError
from app.repos.models import RefreshToken, User

logger = structlog.get_logger(__name__)

# ТЗ 10.1 требует ограничить перебор. Пять попыток — запас для человека, который
# ошибся раскладкой; пятнадцать минут делают перебор бессмысленным, но не превращают
# опечатку в потерю рабочего дня.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)

ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
REFRESH_TOKEN_LIFETIME = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class Session:
    user: User
    refresh_token: str
    refresh_expires_at: datetime


class AuthenticationFailedError(NotAuthenticatedError):
    """Единственная ошибка входа.

    Одна на все случаи намеренно: «нет такого адреса», «неверный пароль» и «учётная
    запись отключена» — три разных ответа, и по разнице между ними перебором выясняется,
    какие адреса заведены в системе.
    """

    code = "authentication-failed"


class CurrentPasswordMismatchError(PermissionDeniedError):
    """Текущий пароль при смене указан неверно.

    Намеренно не `NotAuthenticatedError`: сессия действует, пользователь вошёл, и
    ответ 401 увёл бы его на экран входа за опечатку в одном поле формы. Отдельный
    код нужен интерфейсу, чтобы показать ошибку у нужного поля, а не общим баннером.
    """

    code = "current-password-mismatch"


class AccountLockedError(NotAuthenticatedError):
    """Вход временно закрыт после серии неудачных попыток.

    Отличается от `AuthenticationFailedError` сознательно: человеку нужно понимать, что пароль
    может быть верным, а ждать всё равно придётся. Для перебора это ничего не даёт —
    блокировка наступает и для несуществующих адресов тоже.
    """

    code = "account-locked"


def hash_token(token: str) -> str:
    """SHA-256 достаточно: токен — длинная случайная строка, а не пароль человека.

    Медленное хеширование защищает от перебора коротких секретов; здесь перебирать
    нечего, а проверять токен придётся на каждом обновлении сессии.
    """
    return hashlib.sha256(token.encode()).hexdigest()


async def authenticate(
    session: AsyncSession,
    provider: IdentityProvider,
    credentials: Credentials,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> Session:
    """Вход. Возвращает пользователя и новый токен обновления."""
    now = datetime.now(UTC)
    known_user = await session.scalar(select(User).where(User.email == credentials.login))

    if known_user is not None and known_user.locked_until and known_user.locked_until > now:
        logger.info("login_blocked", user_id=str(known_user.id), until=known_user.locked_until)
        raise AccountLockedError(
            "Вход временно заблокирован после нескольких неудачных попыток. "
            "Повторите через несколько минут."
        )

    user = await provider.authenticate(session, credentials)

    if user is None:
        await _register_failure(session, known_user, now)
        raise AuthenticationFailedError("Неверный адрес или пароль")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now

    refresh_token, record = _issue_refresh_token(user, now, user_agent=user_agent, ip=ip)
    session.add(record)
    await session.flush()

    logger.info("login_succeeded", user_id=str(user.id), provider=provider.name)
    return Session(user=user, refresh_token=refresh_token, refresh_expires_at=record.expires_at)


async def _register_failure(session: AsyncSession, user: User | None, now: datetime) -> None:
    """Считает неудачные попытки.

    Для несуществующего адреса считать нечего — и это не дыра: у перебирающего нет
    способа отличить «адреса нет» от «пароль неверный», ответ в обоих случаях один.
    """
    if user is None:
        return

    user.failed_login_count += 1
    if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
        user.locked_until = now + LOCKOUT_DURATION
        logger.warning("account_locked", user_id=str(user.id), until=user.locked_until)
    await session.flush()


def _issue_refresh_token(
    user: User,
    now: datetime,
    *,
    user_agent: str | None,
    ip: str | None,
) -> tuple[str, RefreshToken]:
    token = secrets.token_urlsafe(48)
    record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=now + REFRESH_TOKEN_LIFETIME,
        user_agent=(user_agent or "")[:300] or None,
        ip=ip,
    )
    return token, record


async def refresh(
    session: AsyncSession,
    token: str,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> Session:
    """Обменивает токен обновления на новый. Старый становится недействительным."""
    now = datetime.now(UTC)
    record = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(token))
    )

    if record is None:
        raise AuthenticationFailedError("Сессия недействительна, войдите заново")

    if record.revoked_at is not None:
        # Токен уже потрачен, но предъявлен снова — значит, он есть у кого-то ещё.
        # Отзываем все сессии пользователя: цена ошибки здесь несоизмерима с неудобством
        # повторного входа.
        await revoke_all(session, record.user_id, reason="reuse_detected")
        logger.warning("refresh_token_reused", user_id=str(record.user_id))
        raise AuthenticationFailedError("Сессия недействительна, войдите заново")

    if record.expires_at <= now:
        raise AuthenticationFailedError("Сессия истекла, войдите заново")

    user = await session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise AuthenticationFailedError("Сессия недействительна, войдите заново")

    new_token, new_record = _issue_refresh_token(user, now, user_agent=user_agent, ip=ip)
    session.add(new_record)
    await session.flush()

    record.revoked_at = now
    record.replaced_by_id = new_record.id
    await session.flush()

    return Session(
        user=user,
        refresh_token=new_token,
        refresh_expires_at=new_record.expires_at,
    )


async def logout(session: AsyncSession, token: str) -> None:
    """Выход. Отзывает предъявленный токен обновления.

    Молчит, если токена нет: сообщать «такой сессии не существует» тому, кто выходит,
    незачем, а различие в ответах — лишний способ что-то узнать о системе.
    """
    record = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(token))
    )
    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        await session.flush()


async def revoke_all(session: AsyncSession, user_id: object, *, reason: str) -> None:
    """Отзывает все действующие сессии пользователя."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.flush()
    logger.info("sessions_revoked", user_id=str(user_id), reason=reason)


async def change_password(
    session: AsyncSession,
    user: User,
    *,
    current_password: str,
    new_password: str,
) -> None:
    """Смена пароля самим пользователем.

    Текущий пароль обязателен, даже когда пользователь уже вошёл: доступ к открытому
    браузеру не должен означать возможность сменить пароль и заблокировать владельца.
    Исключение — первый вход по временному паролю, когда своего пароля ещё нет.
    """
    if user.password_hash is not None and not verify_password(current_password, user.password_hash):
        raise CurrentPasswordMismatchError("Текущий пароль указан неверно")

    validate_password(new_password)

    if user.password_hash is not None and verify_password(new_password, user.password_hash):
        raise RuleViolationError("Новый пароль совпадает с текущим")

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    await session.flush()

    # Смена пароля завершает все прочие сессии: если пароль меняют из-за подозрения на
    # утечку, оставить чужую сессию открытой означает не сделать ничего.
    await revoke_all(session, user.id, reason="password_changed")


def validate_password(password: str) -> None:
    """Только длина, без требований к составу символов.

    Требования вида «заглавная, цифра и знак» дают предсказуемые пароли: Parol2026!
    формально им отвечает. Длина даёт больше.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise RuleViolationError(
            f"Пароль короче {MIN_PASSWORD_LENGTH} символов. "
            "Требований к составу символов нет — длинная фраза надёжнее короткого набора знаков."
        )
