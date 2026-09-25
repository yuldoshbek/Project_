"""Сценарии доступа: выпуск ссылки, открытие сессии, опознание по cookie.

Проверка доступа стоит в одном месте (ADR-0029), и это место — здесь. Роутеры получают
готового пользователя, а не разбираются с токенами; правила токенов живут в
`app.domain.access` и не знают ни про базу, ни про HTTP.

Что важно не потерять при правке:

- **Перевыпуск ссылки гасит сессии.** Иначе тот, кому ссылку переслали, продолжает
  работать, а в «Управлении» написано, что доступ закрыт.
- **Отметка последнего обращения обновляется редко.** Интерфейс опрашивает API раз в
  пятнадцать секунд (ADR-0034), и запись на каждом запросе — это четыре записи в минуту
  ради строки, которую смотрят раз в месяц.
- **Токен не попадает ни в журнал, ни в ответ об ошибке.** В базе лежит отпечаток, в
  ответе — ссылка целиком и только тому, кто её запросил.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.access import (
    MIN_GIVEN_TOKEN_LENGTH,
    SessionWindow,
    fingerprint,
    is_acceptable_given_token,
    is_alive,
    link_for,
    needs_touch,
    new_token,
)
from app.domain.errors import NotAuthenticatedError, NotFoundError, RuleViolationError
from app.repos.models import AccessLink, Session, User


@dataclass(frozen=True, slots=True)
class IssuedLink:
    """Свежая ссылка. Токен существует только в этом ответе — в базе лежит отпечаток."""

    url: str
    issued_at: datetime


@dataclass(frozen=True, slots=True)
class OpenedSession:
    """Открытая сессия: кому она принадлежит и какой токен класть в cookie."""

    user: User
    token: str
    window: SessionWindow


async def issue_link(
    session: AsyncSession,
    *,
    user: User,
    secret: str,
    base_url: str,
    now: datetime,
    token: str | None = None,
) -> IssuedLink:
    """Выпускает пользователю новую ссылку и гасит все его сессии.

    Перевыпуск — это не «обновить адрес», а «закрыть доступ прежнему владельцу ссылки».
    Поэтому сессии гасятся здесь же, а не отдельной кнопкой, которую забудут нажать.

    `token` задаётся только для первой ссылки в облаке (`app.access_cli --token-from-env`):
    его знает заказчик, и печатать ссылку в журнал не нужно. Обычный перевыпуск всегда
    берёт случайный.
    """
    if token is not None and not is_acceptable_given_token(token):
        raise RuleViolationError(
            f"Токен ссылки слишком простой: нужно не меньше {MIN_GIVEN_TOKEN_LENGTH} символов "
            "из латиницы, цифр, «-» и «_»"
        )
    token = token or new_token()
    link = await session.scalar(select(AccessLink).where(AccessLink.user_id == user.id))

    if link is None:
        link = AccessLink(
            user_id=user.id,
            token_fingerprint=fingerprint(token, secret),
            issued_at=now,
        )
        session.add(link)
    else:
        link.token_fingerprint = fingerprint(token, secret)
        link.issued_at = now
        link.last_used_at = None
        link.uses = 0

    await revoke_sessions(session, user_id=user.id, now=now)
    await session.flush()
    return IssuedLink(url=link_for(base_url, token), issued_at=now)


async def open_session(
    session: AsyncSession,
    *,
    token: str,
    secret: str,
    days: int,
    now: datetime,
    ip: str | None = None,
    user_agent: str | None = None,
) -> OpenedSession:
    """Переход по личной ссылке: опознаём владельца и открываем сессию.

    Неизвестный токен — `NotFoundError`, а не «нет доступа»: по ссылке приходит человек,
    а не запрос интерфейса, и различать «ссылка устарела» и «такой ссылки не было» ему
    нечем и незачем.
    """
    link = await session.scalar(
        select(AccessLink).where(AccessLink.token_fingerprint == fingerprint(token, secret))
    )
    if link is None:
        raise NotFoundError("Ссылка недействительна: запросите новую у помощника")

    user = await session.get(User, link.user_id)
    if user is None or not user.is_active:
        raise NotFoundError("Ссылка недействительна: запросите новую у помощника")

    link.last_used_at = now
    link.uses += 1

    session_token = new_token()
    window = SessionWindow.opened(now, days)
    session.add(
        Session(
            user_id=user.id,
            token_fingerprint=fingerprint(session_token, secret),
            expires_at=window.expires_at,
            last_seen_at=now,
            user_agent=(user_agent or None),
            ip=ip,
        )
    )
    await session.flush()
    return OpenedSession(user=user, token=session_token, window=window)


async def resolve(
    session: AsyncSession,
    *,
    token: str,
    secret: str,
    now: datetime,
) -> User:
    """Кто обратился. Нет годной сессии — `NotAuthenticatedError`.

    Именно 401, а не 403: интерфейсу надо показать «откройте систему по своей ссылке», а
    не «вам нельзя». Разница видна руководителю через месяц после последнего входа.
    """
    record = await session.scalar(
        select(Session).where(Session.token_fingerprint == fingerprint(token, secret))
    )
    if record is None or not is_alive(record.expires_at, record.revoked_at, now):
        raise NotAuthenticatedError("Сессия закончилась: откройте ORBITA по своей ссылке")

    user = await session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise NotAuthenticatedError("Сессия закончилась: откройте ORBITA по своей ссылке")

    if needs_touch(record.last_seen_at, now):
        record.last_seen_at = now

    return user


async def revoke_sessions(session: AsyncSession, *, user_id: object, now: datetime) -> None:
    """Гасит действующие сессии пользователя.

    Отметка, а не удаление: в «Управлении» видно, что доступ закрывали, и когда.
    """
    await session.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def active_sessions(
    session: AsyncSession, *, user_id: object, now: datetime
) -> list[Session]:
    """Устройства, с которых сейчас открыт доступ."""
    rows = await session.scalars(
        select(Session)
        .where(
            Session.user_id == user_id,
            Session.revoked_at.is_(None),
            Session.expires_at > now,
        )
        .order_by(Session.last_seen_at.desc().nullslast())
    )
    return list(rows)
