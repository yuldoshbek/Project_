"""Проверки соглашений из CLAUDE.md, которые дешевле поймать тестом, чем на ревью."""

from __future__ import annotations

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
APP = BACKEND_ROOT / "app"


def python_sources() -> list[Path]:
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_create_all() -> None:
    """Схему БД меняет только миграция Alembic (CLAUDE.md, инвариант 7)."""
    offenders = [
        path.relative_to(BACKEND_ROOT)
        for path in python_sources()
        if "create_all" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"create_all в рантайме запрещён, найдено в: {offenders}"


def test_no_naive_utcnow() -> None:
    """Время хранится в UTC как timestamptz; наивные даты запрещены (инвариант 5)."""
    pattern = re.compile(r"datetime\.utcnow\(\)|datetime\.now\(\)\s*$", re.MULTILINE)
    offenders = [
        path.relative_to(BACKEND_ROOT)
        for path in python_sources()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"дата без часового пояса запрещена, используйте datetime.now(UTC): {offenders}"
    )


# Два пути скрыты из схемы осознанно, и оба — не маршруты данных:
#   access.py  — переход по личной ссылке: токен не должен попасть ни в схему, ни в
#                клиент интерфейса, ни в журнал запросов;
#   internal.py — служебный вход расписания: он закрыт секретом в заголовке, а не
#                сессией, и в клиенте интерфейса ему делать нечего.
ALLOWED_TO_HIDE = {"app/api/routes/access.py", "app/api/routes/internal.py"}


def test_no_route_hides_from_the_schema() -> None:
    """Маршрут данных не исключают из описания API (`include_in_schema=False`).

    Схема — не украшение: по ней собирается клиент интерфейса, и по ней же обходит все
    маршруты проверка «ни один не отвечает без сессии» (`test_access`). Спрятанный из
    схемы эндпоинт выпадает из обоих — и незаметнее всего из второго.
    """
    offenders = [
        path.relative_to(BACKEND_ROOT).as_posix()
        for path in python_sources()
        if "include_in_schema" in path.read_text(encoding="utf-8")
        and path.relative_to(BACKEND_ROOT).as_posix() not in ALLOWED_TO_HIDE
    ]
    assert not offenders, f"маршрут, скрытый из схемы, не попадёт под проверку доступа: {offenders}"
