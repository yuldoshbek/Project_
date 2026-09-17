"""Команда назначения пароля (ORB-006).

**Зачем этот файл появился.** До 17.09 у `app/cli.py` не было ни одного теста, и
команда `set-password` печатала «пароль назначен», не записывая ничего: `return` из тела
`async for` закрывал асинхронный генератор `session_scope`, фиксация стояла у него после
`yield`, а `GeneratorExit` — не наследник `Exception`, поэтому не срабатывала ни ветка
откатa, ни ветка фиксации. Сообщение печаталось до фиксации и потому печаталось всегда.

Дефект обнаружился не чтением кода, а попыткой войти на стенд назначенным паролем.
Поэтому проверка здесь идёт **через запуск команды процессом и чтение базы отдельным
подключением**: тест, вызывающий `_set_password` внутри откатываемой транзакции теста,
остался бы зелёным и до исправления — ровно потому, что фиксацию он бы и не проверял.

Отдельная база и отдельное подключение здесь не перестраховка, а единственный способ
отличить «записано» от «записано и потеряно».
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

from app.adapters.passwords import verify_password

BACKEND_ROOT = Path(__file__).resolve().parent.parent

FIRST = "Первый-пароль-стенда-1"
SECOND = "Второй-пароль-стенда-2"
ASSISTANT = "assistant@orbita.local"


def run_cli(*args: str, database: str, stdin: str) -> subprocess.CompletedProcess[str]:
    """Запускает команду процессом, как её запускает человек.

    Не вызовом функции: проверяется в том числе то, что фиксация случилась в её
    собственной транзакции и переживает завершение процесса. Вызов в тесте разделил бы
    с тестом соединение, и потерянная фиксация осталась бы незамеченной.
    """
    env = {
        **os.environ,
        "ORBITA_DB_NAME": database,
        "ORBITA_SECRET_KEY": "тестовый-ключ-достаточной-длины-не-для-эксплуатации",
        "ORBITA_ENV": "test",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    return subprocess.run(  # noqa: S603
        [sys.executable, "-X", "utf8", "-m", "app.cli", *args],
        cwd=BACKEND_ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


async def stored(db: asyncpg.Connection, email: str) -> tuple[str | None, bool | None]:
    """Хеш и признак временного пароля — прямо из базы, в обход ORM и кешей сессии."""
    row = await db.fetchrow(
        "select password_hash, must_change_password from orbita.users where email = $1", email
    )
    if row is None:
        return None, None
    return row["password_hash"], row["must_change_password"]


class TestSetPasswordActuallyWrites:
    """Единственное обещание команды: после её успеха паролем можно войти."""

    async def test_password_survives_the_end_of_the_process(
        self, db: asyncpg.Connection, migrated_database: str
    ) -> None:
        """Тот самый случай, который печатал успех и не записывал ничего.

        Проверяется не код возврата и не сообщение, а **состояние базы, прочитанное
        другим подключением**. Сообщение об успехе — сторона, которая и врала.
        """
        before, _ = await stored(db, ASSISTANT)

        result = run_cli("set-password", ASSISTANT, database=migrated_database, stdin=FIRST)

        assert result.returncode == 0, f"{result.stdout} {result.stderr}"
        assert "назначен" in result.stdout

        after, must_change = await stored(db, ASSISTANT)
        assert after is not None
        assert after != before, "команда сообщила об успехе, а хеш в базе не изменился"
        assert verify_password(FIRST, after), "записан не тот пароль, который назначали"

        # Пароль назначен администратором, значит владелец знает его не один: система
        # обязана потребовать замену при первом входе.
        assert must_change is True

    async def test_second_call_replaces_the_first_password(
        self, db: asyncpg.Connection, migrated_database: str
    ) -> None:
        """Повторное назначение заменяет пароль, а не добавляет второй.

        Проверяется обоими способами: новый пароль подходит, старый — нет. Без второй
        половины тест прошёл бы и в случае, когда запись не произошла вовсе, а
        подходящим остался прежний пароль.
        """
        run_cli("set-password", ASSISTANT, database=migrated_database, stdin=FIRST)
        run_cli("set-password", ASSISTANT, database=migrated_database, stdin=SECOND)

        stored_hash, _ = await stored(db, ASSISTANT)
        assert stored_hash is not None
        assert verify_password(SECOND, stored_hash)
        assert not verify_password(FIRST, stored_hash)

    async def test_unknown_address_changes_nothing_and_says_where_to_look(
        self, db: asyncpg.Connection, migrated_database: str
    ) -> None:
        before, must_change_before = await stored(db, ASSISTANT)

        result = run_cli(
            "set-password", "никого@orbita.local", database=migrated_database, stdin=FIRST
        )

        assert result.returncode == 1
        # Отказ уходит в поток ошибок, а не в вывод: вывод команды читают скрипты.
        assert "не найден" in result.stderr
        assert "make seed" in result.stderr, "непонятно, что делать дальше"

        after, must_change_after = await stored(db, ASSISTANT)
        assert (after, must_change_after) == (before, must_change_before)

    async def test_weak_password_is_refused_before_anything_is_written(
        self, db: asyncpg.Connection, migrated_database: str
    ) -> None:
        """Слабый пароль — отказ, и база при этом не тронута.

        Важна вторая половина: проверка стоит **после** чтения пользователя, и порядок
        строк в функции решает, останется ли в базе половина изменения.
        """
        before = await stored(db, ASSISTANT)

        result = run_cli("set-password", ASSISTANT, database=migrated_database, stdin="123")

        assert result.returncode != 0
        assert await stored(db, ASSISTANT) == before

    async def test_empty_input_is_refused_rather_than_accepted_as_a_password(
        self, db: asyncpg.Connection, migrated_database: str
    ) -> None:
        """Пустой ввод при перенаправлении — отказ, а не пустой пароль.

        Случай не выдуманный: так выглядит `make set-password` без ответа на подсказку и
        так выглядит пустой файл в развёртывании.
        """
        before = await stored(db, ASSISTANT)

        result = run_cli("set-password", ASSISTANT, database=migrated_database, stdin="")

        assert result.returncode == 1
        assert "не передан" in result.stderr
        assert await stored(db, ASSISTANT) == before


class TestUsage:
    async def test_without_arguments_explains_how_to_call_it(self, migrated_database: str) -> None:
        result = run_cli(database=migrated_database, stdin="")

        assert result.returncode == 2
        assert "Использование" in result.stderr

    async def test_unknown_command_is_not_silently_ignored(self, migrated_database: str) -> None:
        result = run_cli("подними-всё", database=migrated_database, stdin="")

        assert result.returncode == 2


@pytest.fixture(autouse=True)
async def _leave_the_account_as_seeds_left_it(db: asyncpg.Connection) -> AsyncIterator[None]:
    """Возвращает учётную запись в состояние сидов: пароля нет, замена требуется.

    Команда фиксирует изменения по-настоящему, и внешняя транзакция теста их не
    откатывает — иначе этот файл не проверял бы ничего. Значит, убирать за собой надо
    руками, и делать это **после** каждого теста: иначе тесты входа, идущие следом,
    получат пароль, о котором не просили, и упадут по причине, к ним не относящейся.

    Заодно убираются выданные токены обновления: команда их отзывает, и оставленные
    строки мешали бы соседям так же, как оставленный пароль.
    """
    yield
    await db.execute(
        "update orbita.users set password_hash = null, must_change_password = true, "
        "failed_login_count = 0, locked_until = null"
    )
    await db.execute("delete from orbita.refresh_tokens")
