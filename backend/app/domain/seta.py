"""События SETA по поручениям Ижро — домен порта `SetaGateway` (ТЗ 10, PLAN, блок 3).

SETA пока не подключается: подключение — вне плана до отдельного решения заказчика
(docs/PLAN.md). Порт нужен, чтобы подключение стало заменой адаптера, а не переписыванием:
события по поручениям — принято, начато, сдано, продлено — уже входят в признак жизни
поручения рядом с контрольной отметкой и движением задачи (`app.domain.ijro.LifeSource.SETA`,
вклад вносит `app.services.metrics.seta_life`). Без подключения событий нет, и вклад пуст.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SetaEventKind(StrEnum):
    """Что SETA сообщает о поручении (ТЗ 10)."""

    ACCEPTED = "accepted"
    STARTED = "started"
    SUBMITTED = "submitted"
    EXTENDED = "extended"


def assignment_key(document_code: str, band: str | None) -> str:
    """Номер поручения так, как его называет таблица Ижро: документ и пункт — «ПФ-155/9-банд».

    Другого общего ключа у двух систем нет: код записи (`IJR-2026-0042`) ORBITA присваивает
    сама при привозе, и SETA его не знает. Документ — нормализованный номер, тот же, что
    склеивает написания при привозе. Точный вид номера в SETA подтверждается при
    подключении (ТЗ 10): тогда меняется эта функция, а не расчёт признака жизни.
    """
    return f"{document_code}/{band}" if band else document_code


@dataclass(frozen=True, slots=True)
class SetaEvent:
    """Событие по поручению. Поручение — по номеру из таблицы Ижро (`assignment_key`)."""

    assignment_code: str
    kind: SetaEventKind
    at: datetime


def latest_by_assignment(events: Iterable[SetaEvent]) -> dict[str, datetime]:
    """Самое свежее событие по каждому поручению — вклад SETA в признак жизни.

    Признак жизни — самое свежее из событий (ТЗ 4), поэтому от SETA нужен один момент на
    поручение, а не лента.
    """
    latest: dict[str, datetime] = {}
    for event in events:
        known = latest.get(event.assignment_code)
        if known is None or event.at > known:
            latest[event.assignment_code] = event.at
    return latest
