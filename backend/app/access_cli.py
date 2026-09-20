"""Выпуск личной ссылки из командной строки.

Нужен ровно там, где иначе замкнутый круг: чтобы перевыпустить ссылку в разделе
«Управление», надо уже быть в системе, а первая ссылка после первой выкладки берётся
неоткуда. Здесь она и берётся.

    uv run python -m app.access_cli assistant
    uv run python -m app.access_cli leader --base-url https://orbita.netlify.app

Второе применение — восстановление: помощник потерял доступ, перевыпустить некому.

Ссылка печатается один раз и в журнал не пишется. Передавать её надо тем же способом, что
и любой секрет: одним сообщением, без пересылки дальше.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.people import Role
from app.repos.database import dispose_database, init_database, session_scope
from app.repos.models import User
from app.services import access
from app.settings import get_settings


async def issue(role: Role, base_url: str | None) -> int:
    settings = get_settings()
    init_database(settings)
    try:
        async for session in session_scope():
            user = await session.scalar(select(User).where(User.role == role.value, User.is_active))
            if user is None:
                print(f"в базе нет пользователя с ролью «{role.value}»: загрузите справочники")
                return 1

            issued = await access.issue_link(
                session,
                user=user,
                secret=settings.session_secret.get_secret_value(),
                base_url=base_url or settings.base_url,
                now=datetime.now(UTC),
            )
            print(issued.url)
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
    args = parser.parse_args()
    return asyncio.run(issue(Role(args.role), args.base_url))


if __name__ == "__main__":
    raise SystemExit(cli())
