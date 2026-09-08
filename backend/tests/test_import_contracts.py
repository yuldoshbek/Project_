"""Проверка границ слоёв (CLAUDE.md, раздел «Архитектура»).

Смысл теста — не в том, что контракты описаны в pyproject.toml, а в том, что они
действительно срабатывают. Поэтому тест не только запускает lint-imports на чистом
дереве, но и намеренно вносит нарушение и убеждается, что оно поймано.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
VIOLATION = BACKEND_ROOT / "app" / "domain" / "_layer_violation_probe.py"


def lint_imports_executable() -> Path:
    """Путь к консольной команде lint-imports внутри текущего окружения.

    Через `python -m importlinter.cli` запускать нельзя: модуль импортируется, но
    команда click не выполняется — процесс молча возвращает 0, и тест становится
    бесполезным.
    """
    bin_dir = Path(sys.executable).parent
    for name in ("lint-imports.exe", "lint-imports"):
        candidate = bin_dir / name
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"lint-imports не найден в {bin_dir}; выполните uv sync --all-groups")


def run_lint_imports() -> subprocess.CompletedProcess[str]:
    # S603: путь берётся из sys.executable текущего окружения, пользовательского ввода нет.
    return subprocess.run(  # noqa: S603
        [str(lint_imports_executable())],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        # Без явной кодировки Windows читает вывод в cp1251 и падает на рамках отчёта.
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_layers_are_clean() -> None:
    """На текущем коде границы слоёв не нарушены."""
    result = run_lint_imports()
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_violation_is_detected() -> None:
    """Домен, импортирующий api, должен ронять проверку.

    Если этот тест зелёный без правок кода — контракт не работает и не защищает ничего.
    """
    VIOLATION.write_text(
        "from app.api import *  # noqa: F401,F403\n",
        encoding="utf-8",
    )
    try:
        result = run_lint_imports()
    finally:
        VIOLATION.unlink(missing_ok=True)

    assert result.returncode != 0, (
        "import-linter пропустил импорт app.api из app.domain — контракт слоёв не работает"
    )


@pytest.mark.parametrize("layer", ["api", "services", "domain", "repos", "adapters", "workers"])
def test_layer_package_exists(layer: str) -> None:
    """Все слои из CLAUDE.md существуют: контракт ссылается на реальные пакеты."""
    assert (BACKEND_ROOT / "app" / layer / "__init__.py").is_file()
