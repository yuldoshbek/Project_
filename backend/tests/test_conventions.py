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
