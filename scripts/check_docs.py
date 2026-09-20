#!/usr/bin/env python3
"""Проверки документации, которые дешевле автоматизировать, чем ловить глазами.

1. Внутренние ссылки в markdown ведут в существующие файлы.
2. Документы плана и требований на месте.

Нумерация тикетов не проверяется: с 20.09.2026 работа идёт блоками (docs/PLAN.md),
отдельных карточек нет.

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


def check_key_documents(errors: list[str]) -> None:
    """Документы, на которые опирается весь процесс, должны существовать."""
    required = [
        "tz/TZ-ORBITA-v2.0.md",
        "CLAUDE.md",
        "docs/PLAN.md",
        "docs/CONTEXT.md",
        "docs/ARCHITECTURE.md",
        "docs/OPEN-QUESTIONS.md",
    ]
    missing = [name for name in required if not (ROOT / name).exists()]
    if missing:
        errors.append(f"нет обязательных документов: {', '.join(missing)}")
    else:
        print(f"обязательных документов на месте: {len(required)}")


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
    check_key_documents(errors)
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
