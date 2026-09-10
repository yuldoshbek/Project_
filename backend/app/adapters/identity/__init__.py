"""Порт установления личности.

Сегодня вход локальный: адрес и пароль. Завтра — через ассистента SETA, когда у него
появится API ([ADR-0001](../../../../docs/adr/ADR-0001-architecture-variant.md)). Замена
не должна затрагивать ни роутеры, ни экраны — только строку в настройках.

Протокол намеренно узкий: он отвечает на вопрос «кто это», и ничего не знает ни про
токены, ни про роли. Токены выдаёт `app.services.auth`, роли живут в записи пользователя.
Провайдер, который сам выдаёт токены, невозможно подменить, не переписав всё остальное.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import User


@dataclass(frozen=True, slots=True)
class Credentials:
    """То, чем пользователь доказывает, что он — это он.

    Для локального провайдера это адрес и пароль; для SETA будет подпись Telegram.
    Провайдер сам решает, что из этого ему нужно.
    """

    login: str
    secret: str


class IdentityProvider(Protocol):
    """Устанавливает личность по учётным данным."""

    name: str

    async def authenticate(self, session: AsyncSession, credentials: Credentials) -> User | None:
        """Возвращает пользователя либо `None`.

        Причину отказа наружу не сообщает намеренно: «нет такого адреса» и «неверный
        пароль» — это два разных ответа, и по разнице между ними перебором выясняется,
        какие адреса заведены в системе.
        """
        ...


def create_identity_provider(name: str) -> IdentityProvider:
    """Провайдер по имени из настроек.

    Неизвестное имя роняет приложение на старте, а не молча включает вход по паролю
    там, где ожидали вход через SETA.
    """
    from app.adapters.identity.local import LocalIdentityProvider

    providers: dict[str, IdentityProvider] = {"local": LocalIdentityProvider()}

    if name not in providers:
        raise ValueError(
            f"неизвестный провайдер личности {name!r}; доступны: {sorted(providers)}. "
            "Провайдер SETA появится вместе с её API (ADR-0001)."
        )
    return providers[name]
