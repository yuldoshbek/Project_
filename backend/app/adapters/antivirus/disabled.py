"""Проверка выключена.

Называется честно — `NoScanner`, а не `SimpleScanner` или `DefaultScanner`. Заглушка с
успокаивающим именем однажды окажется на рабочем контуре, и никто не заметит: в списке
настроек `antivirus = default` читается как «обычная проверка», а не как «проверок нет».

Отдельная запись в лог при каждой загрузке — по той же причине. Выключенный антивирус
должен оставлять след там, где его ищут при разборе, а не только в файле настроек.
"""

from __future__ import annotations

import structlog

from app.adapters.antivirus import ScanResult

logger = structlog.get_logger(__name__)


class NoScanner:
    """Ничего не проверяет и говорит об этом."""

    name = "disabled"

    async def scan(self, data: bytes) -> ScanResult:
        logger.warning("antivirus_disabled", size=len(data))
        return ScanResult(is_clean=True)
