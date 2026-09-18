#!/usr/bin/env python3
"""Проверки документации, которые дешевле автоматизировать, чем ловить глазами.

1. Нумерация тикетов: без дублей.
2. Внутренние ссылки в markdown ведут в существующие файлы.

Проверка разрывов в нумерации снята 18.09.2026. Она предполагала одну сплошную нумерацию
ORB-001…098, а после сужения объёма счёт начат заново с ORB-100: разрыв между старым и
новым диапазоном — не ошибка, а след переворота. Дубли проверять по-прежнему стоит: два
тикета с одним номером — это два агента, которые однажды возьмут одну работу.

`docs/archive/` не проверяется: документы прежнего объёма заморожены, их относительные
ссылки сломались при переезде на уровень ниже, и чинить их незачем — они не действуют.

Запуск: python scripts/check_docs.py (из корня репозитория).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TICKET_RE = re.compile(r"^## ORB-(\d{3})\b", re.MULTILINE)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SKIP_DIRS = {".git", "node_modules", ".venv", "dist", "tz", "archive"}


def markdown_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*.md")
        if not SKIP_DIRS & set(path.relative_to(ROOT).parts)
    ]


def check_ticket_numbering(errors: list[str]) -> None:
    numbers: list[int] = []
    for path in sorted((ROOT / "docs" / "tickets").glob("*.md")):
        if path.name == "INDEX.md":
            continue
        numbers.extend(
            int(n) for n in TICKET_RE.findall(path.read_text(encoding="utf-8"))
        )

    duplicates = {n for n in numbers if numbers.count(n) > 1}
    if duplicates:
        errors.append(f"дублирующиеся номера тикетов: {sorted(duplicates)}")

    ordered = sorted(set(numbers))
    if not ordered:
        errors.append("не найдено ни одного тикета в docs/tickets")
        return

    print(
        f"тикетов с карточками: {len(ordered)} (ORB-{ordered[0]:03d}…ORB-{ordered[-1]:03d})"
    )


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
