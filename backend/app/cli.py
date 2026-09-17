"""Служебные команды.

Запуск: `python -m app.cli <команда>` или `make password EMAIL=...`.

Здесь живёт то, что нельзя делать через интерфейс: назначение первичного пароля. В сидах
пароля нет намеренно (репозиторий публичный), а без него в систему не войти — эта команда
закрывает разрыв.
"""

from __future__ import annotations

import asyncio
import getpass
import sys

from sqlalchemy import select

from app.adapters.passwords import hash_password
from app.observability import configure_logging
from app.repos.database import dispose_database, init_database, session_scope
from app.repos.models import User
from app.services.auth import revoke_all, validate_password
from app.settings import get_settings


async def _set_password(email: str, password: str) -> int:
    """Назначает пароль и фиксирует его.

    **Из тела `async for` здесь нельзя выходить `return`.** `session_scope` —
    асинхронный генератор, и фиксация стоит у него после `yield`; выход из цикла
    закрывает генератор, поднимая в точке `yield` `GeneratorExit`. Он не наследник
    `Exception`, поэтому ни ветка откатa, ни ветка фиксации не срабатывают — сессия
    просто закрывается, и записанное теряется.

    Так и было до 17.09: команда печатала «пароль назначен» и не записывала ничего.
    Признаком успеха служило сообщение, а оно печаталось до фиксации, поэтому команда
    сообщала об успехе всегда. Теперь сообщение печатается **после** цикла, когда
    фиксация уже произошла: печатать успех до записи — значит иметь инструмент, который
    врёт по построению, а не по ошибке.

    `break` для «пользователь не найден» безопасен: до него ничего не записано, и откат
    закрытого генератора терять нечего.
    """
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=False)
    init_database(settings)

    saved = False
    try:
        async for session in session_scope():
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                print(f"Пользователь {email!r} не найден.", file=sys.stderr)
                print("Заведите его командой make seed или в администрировании.", file=sys.stderr)
                break

            validate_password(password)
            user.password_hash = hash_password(password)
            # Пароль назначен администратором, значит владелец его знает не один:
            # при первом входе система потребует заменить.
            user.must_change_password = True
            await revoke_all(session, user.id, reason="password_set_by_admin")
            saved = True
    finally:
        await dispose_database()

    if not saved:
        return 1

    print(f"Пароль для {email} назначен. При первом входе система попросит его сменить.")
    return 0


def read_password(email: str) -> str | None:
    """Читает пароль скрытым вводом, а при перенаправлении — из стандартного ввода.

    Из аргументов командной строки пароль не берётся никогда: аргументы видны в
    списке процессов и остаются в истории оболочки — то есть пароль оказался бы
    записан на диск раньше, чем дошёл до базы.

    Проверка на терминал нужна для скриптов и развёртывания: `getpass` в этих условиях
    читает не оттуда и просто зависает, ожидая ввода, которого не будет.
    """
    if not sys.stdin.isatty():
        lines = sys.stdin.read().splitlines()
        if not lines or not lines[0]:
            print("Пароль не передан на стандартный ввод.", file=sys.stderr)
            return None
        return lines[0]

    password = getpass.getpass(f"Новый пароль для {email}: ")
    repeat = getpass.getpass("Повторите: ")

    if password != repeat:
        print("Пароли не совпадают.", file=sys.stderr)
        return None

    return password


def set_password(email: str) -> int:
    password = read_password(email)
    if password is None:
        return 1
    return asyncio.run(_set_password(email, password))


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv

    if len(arguments) == 2 and arguments[0] == "set-password":
        return set_password(arguments[1])

    print("Использование: python -m app.cli set-password <адрес>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
