"""Выпуск личной ссылки из командной строки.

Нужен ровно там, где иначе замкнутый круг: чтобы перевыпустить ссылку в разделе
«Управление», надо уже быть в системе, а первая ссылка после первой выкладки берётся
неоткуда. Здесь она и берётся.

    uv run python -m app.access_cli assistant
    uv run python -m app.access_cli leader --base-url https://orbita.netlify.app

Второе применение — восстановление: помощник потерял доступ, перевыпустить некому.

Ссылка печатается один раз и в журнал не пишется. Передавать её надо тем же способом, что
и любой секрет: одним сообщением, без пересылки дальше.

**Первая ссылка в облаке** выпускается прогоном GitHub Actions, а его журнал в публичном
репозитории читает кто угодно. Поэтому там ссылка не печатается вовсе: токен задаёт
заказчик секретом, прогон кладёт в базу только его отпечаток, а ссылку заказчик собирает
сам — `<адрес>/api/access/<токен из секрета>`:

    uv run python -m app.access_cli assistant --token-from-env ORBITA_FIRST_ACCESS_TOKEN \
        --only-if-missing

`--only-if-missing` делает команду безопасной для каждой выкладки: ссылка, которая уже
есть, не перевыпускается, и открытые сессии не гаснут.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.errors import RuleViolationError
from app.domain.people import Role
from app.repos.database import dispose_database, init_database, session_scope
from app.repos.models import AccessLink, User
from app.services import access
from app.settings import get_settings


async def issue(
    role: Role,
    base_url: str | None,
    *,
    token_variable: str | None = None,
    only_if_missing: bool = False,
) -> int:
    settings = get_settings()
    token: str | None = None
    if token_variable is not None:
        token = os.environ.get(token_variable, "").strip()
        if not token:
            print(f"переменная {token_variable} пуста: токен первой ссылки не задан")
            return 1

    init_database(settings)
    try:
        async for session in session_scope():
            user = await session.scalar(select(User).where(User.role == role.value, User.is_active))
            if user is None:
                print(f"в базе нет пользователя с ролью «{role.value}»: загрузите справочники")
                return 1

            if only_if_missing and await session.scalar(
                select(AccessLink.id).where(AccessLink.user_id == user.id)
            ):
                print(f"у роли «{role.value}» ссылка уже есть — не перевыпускаю")
                return 0

            try:
                issued = await access.issue_link(
                    session,
                    user=user,
                    secret=settings.session_secret.get_secret_value(),
                    base_url=base_url or settings.base_url,
                    now=datetime.now(UTC),
                    token=token,
                )
            except RuleViolationError as error:
                print(error.message)
                return 1

            if token is None:
                print(issued.url)
            else:
                # Ссылка содержит токен из секрета — в журнал прогона она не попадает.
                print(f"ссылка роли «{role.value}» выпущена по токену из {token_variable}")
    finally:
        await dispose_database()
    return 0


def cli() -> int:
    parser = argparse.ArgumentParser(description="Выпустить личную ссылку доступа")
    parser.add_argument("role", choices=[role.value for role in Role], help="кому")
    parser.add_argument(
        "--base-url",
        default=None,
        help="адрес интерфейса, если он отличается от настроек (ORBITA_BASE_URL)",
    )
    parser.add_argument(
        "--token-from-env",
        default=None,
        metavar="ПЕРЕМЕННАЯ",
        help="взять токен из переменной окружения и не печатать ссылку (первая ссылка в облаке)",
    )
    parser.add_argument(
        "--only-if-missing",
        action="store_true",
        help="ничего не делать, если у роли ссылка уже есть",
    )
    args = parser.parse_args()
    return asyncio.run(
        issue(
            Role(args.role),
            args.base_url,
            token_variable=args.token_from_env,
            only_if_missing=args.only_if_missing,
        )
    )


if __name__ == "__main__":
    raise SystemExit(cli())
