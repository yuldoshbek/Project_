#!/usr/bin/env python3
"""Проверки документации, которые дешевле автоматизировать, чем ловить глазами.

1. Нумерация тикетов: без дублей и без разрывов.
2. Внутренние ссылки в markdown ведут в существующие файлы.
3. Каждый ADR, на который ссылаются, существует.

Запуск: python scripts/check_docs.py (из корня репозитория).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TICKET_RE = re.compile(r"^## ORB-(\d{3})\b", re.MULTILINE)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SKIP_DIRS = {".git", "node_modules", ".venv", "dist", "tz"}


def markdown_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*.md")
        if not SKIP_DIRS & set(path.relative_to(ROOT).parts)
    ]


def check_ticket_numbering(errors: list[str]) -> None:
    numbers: list[int] = []
    for path in sorted((ROOT / "docs" / "tickets").glob("E*.md")):
        numbers.extend(int(n) for n in TICKET_RE.findall(path.read_text(encoding="utf-8")))

    duplicates = {n for n in numbers if numbers.count(n) > 1}
    if duplicates:
        errors.append(f"дублирующиеся номера тикетов: {sorted(duplicates)}")

    ordered = sorted(set(numbers))
    if not ordered:
        errors.append("не найдено ни одного тикета в docs/tickets")
        return

    expected = list(range(ordered[0], ordered[-1] + 1))
    missing = sorted(set(expected) - set(ordered))
    if missing:
        errors.append(f"разрывы в нумерации тикетов: {missing}")

    print(f"тикетов: {len(ordered)} (ORB-{ordered[0]:03d}…ORB-{ordered[-1]:03d})")


def check_links(errors: list[str]) -> None:
    checked = 0
    for path in markdown_files():
        for target in LINK_RE.findall(path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            checked += 1
            if not resolved.exists():
                errors.append(f"битая ссылка в {path.relative_to(ROOT)}: {target}")
    print(f"проверено внутренних ссылок: {checked}")


def main() -> int:
    errors: list[str] = []
    check_ticket_numbering(errors)
    check_links(errors)

    if errors:
        print("\nОшибки:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("документы в порядке")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
