#!/usr/bin/env python3
"""Проверка машины перед работой: `make doctor`.

За два дня работы четыре круга «правка — прогон — падение — правка» ушли не на код, а на
окружение: контейнер базы без опубликованного порта, чужая база SETA на том же порту,
потерянный BOM в `make.ps1`, `npm` вместо `npm.cmd`. Общее у них одно — окружение
проверялось после работы, а не до неё.

Этот скрипт отвечает за десять секунд на вопрос «можно ли начинать». Он ничего не чинит:
чинить окружение молча — значит однажды починить не то. Он называет, что не так, и чем это
лечится.

Запуск: python scripts/doctor.py (из корня репозитория).
Код возврата 1 — работать нельзя; предупреждения на код возврата не влияют.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = sys.platform == "win32"

OK = "  ok"
WARN = "  ~ "
FAIL = "  ! "

problems: list[str] = []
warnings: list[str] = []


def say(mark: str, text: str, hint: str | None = None) -> None:
    print(f"{mark} {text}")
    if hint:
        print(f"      {hint}")


def fails(text: str, hint: str) -> None:
    problems.append(text)
    say(FAIL, text, hint)


def warns(text: str, hint: str) -> None:
    warnings.append(text)
    say(WARN, text, hint)


def env_values() -> dict[str, str]:
    """Значения из .env. Без внешних библиотек: файл простой, а зависимость — нет."""
    path = ROOT / ".env"
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def check_tools() -> None:
    """Инструменты, без которых ни одна цель Makefile не работает."""
    required = {
        "uv": "https://docs.astral.sh/uv/ — им ставится Python и зависимости backend",
        "docker": "Docker Desktop — им поднимается PostgreSQL для разработки",
        "git": "без него нет ни ветки, ни коммита",
    }
    # На Windows npm вызывается через npm.cmd: `npm` разрешается в npm.ps1, который
    # собирает команду строкой и ломается на кавычках в аргументах.
    required["npm.cmd" if IS_WINDOWS else "npm"] = "Node.js 22 — им собирается интерфейс"

    for tool, hint in required.items():
        if shutil.which(tool):
            say(OK, f"{tool} найден")
        else:
            fails(f"{tool} не найден", f"Поставьте: {hint}")


def check_env_file() -> dict[str, str]:
    """Набор ключей в .env должен совпадать с .env.example.

    Не значения — их знать неоткуда, — а именно набор: переменная, добавленная в пример и
    забытая в рабочем файле, проявляется падением на старте приложения, а не здесь.
    """
    example = ROOT / ".env.example"
    actual = ROOT / ".env"

    if not actual.exists():
        fails(".env не найден", "Скопируйте: cp .env.example .env и заполните секреты")
        return {}

    keys = re.compile(r"^([A-Z_]+)=", re.MULTILINE)
    expected = set(keys.findall(example.read_text(encoding="utf-8")))
    present = set(keys.findall(actual.read_text(encoding="utf-8")))

    missing = sorted(expected - present)
    if missing:
        fails(
            f".env не хватает ключей: {', '.join(missing)}",
            "Сверьтесь с .env.example: приложение упадёт на старте, а не здесь",
        )
    else:
        say(OK, f".env на месте, ключей {len(present)}")

    return env_values()


def check_secrets(values: dict[str, str]) -> None:
    """Длина ключей проверяется здесь по той же причине, что и в settings.py."""
    session = values.get("ORBITA_SESSION_SECRET", "")
    jobs = values.get("ORBITA_JOBS_SECRET", "")

    if len(session) < 32:
        fails(
            "ORBITA_SESSION_SECRET короче 32 символов",
            'Сгенерируйте: python -c "import secrets; print(secrets.token_urlsafe(48))"',
        )
    if len(jobs) < 16 or not jobs.isascii():
        fails(
            "ORBITA_JOBS_SECRET короче 16 символов или не латиница",
            "Секрет едет в заголовке HTTP: кириллицу туда не отправить",
        )
    if len(session) >= 32 and len(jobs) >= 16 and jobs.isascii():
        say(OK, "секреты заданы и достаточной длины")


def check_database(values: dict[str, str]) -> None:
    """Порт слушает — и слушает **наша** база, а не соседняя.

    Проверка на имя базы не придирка: ORBITA и ассистент SETA стоят на одной машине, и
    один раз миграции уже пошли в чужой контейнер, потому что порт совпал.
    """
    host = values.get("ORBITA_DB_HOST", "127.0.0.1")
    port = int(values.get("ORBITA_DB_PORT", "55433"))
    name = values.get("ORBITA_DB_NAME", "orbita")

    with socket.socket() as probe:
        probe.settimeout(1.5)
        if probe.connect_ex((host, port)) != 0:
            fails(
                f"на {host}:{port} никто не слушает",
                "Поднимите базу: make up (или ./make.ps1 up)",
            )
            return

    say(OK, f"{host}:{port} отвечает")

    docker = shutil.which("docker")
    if docker is None:
        return

    # Полный путь, а не имя: запускается ровно тот docker, который найден выше.
    # Исключение S603 здесь честное: путь дал shutil.which, аргументы — литералы,
    # пользовательского ввода в команде нет вовсе.
    found = subprocess.run(  # noqa: S603
        [docker, "compose", "ps", "--format", "{{.Service}} {{.Publishers}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if found.returncode != 0:
        warns(
            "docker compose ps не отработал — чей это порт, проверить нечем",
            "Убедитесь, что запущен Docker Desktop",
        )
        return

    if str(port) in found.stdout:
        say(OK, f"порт {port} опубликован контейнером ORBITA, база «{name}»")
    else:
        warns(
            f"порт {port} слушает не контейнер ORBITA",
            "Возможно, это база соседнего проекта: миграции уйдут в чужую схему",
        )


def check_migrations() -> None:
    """Голова миграций должна быть одна — две означают неопределённый порядок наката."""
    uv = shutil.which("uv")
    if uv is None:
        return

    found = subprocess.run(  # noqa: S603  — путь от shutil.which, аргументы литеральные
        [uv, "run", "alembic", "heads"],
        cwd=ROOT / "backend",
        capture_output=True,
        text=True,
        check=False,
    )
    if found.returncode != 0:
        warns(
            "alembic heads не отработал",
            "Обычно это незаполненный .env или не установленные зависимости: make install",
        )
        return

    heads = [line for line in found.stdout.splitlines() if line.strip()]
    if len(heads) == 1:
        say(OK, f"голова миграций одна: {heads[0].split()[0]}")
    else:
        fails(
            f"голов миграций {len(heads)}",
            "Две ветки независимо добавили миграции: сведите их до слияния",
        )


def check_encoding() -> None:
    """make.ps1 обязан начинаться с BOM.

    Без него PowerShell 5.1 читает файл как ANSI, русские строки превращаются в мусор, и
    скрипт падает на разборе. Один раз это уже случилось.
    """
    if not IS_WINDOWS:
        return
    head = (ROOT / "make.ps1").read_bytes()[:3]
    if head == b"\xef\xbb\xbf":
        say(OK, "make.ps1 с BOM — PowerShell прочитает кириллицу")
    else:
        fails(
            "make.ps1 без BOM",
            "PowerShell 5.1 прочитает его как ANSI и упадёт на разборе русских строк",
        )


def main() -> int:
    print(f"ORBITA — проверка окружения ({'Windows' if IS_WINDOWS else os.name})\n")

    check_tools()
    values = check_env_file()
    if values:
        check_secrets(values)
        check_database(values)
    check_migrations()
    check_encoding()

    print()
    if problems:
        print(f"Работать нельзя: {len(problems)} шт. — см. пометки «!» выше.")
        return 1
    if warnings:
        print(f"Можно работать. Предупреждений: {len(warnings)} — см. пометки «~».")
        return 0
    print("Всё на месте.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
