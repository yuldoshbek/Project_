"""События SETA по поручениям Ижро — домен порта `SetaGateway` (ТЗ 11, PLAN, блок 3).

SETA пока не подключается: подключение — вне плана до отдельного решения заказчика
(docs/PLAN.md). Порт нужен, чтобы подключение стало заменой адаптера, а не переписыванием:
события по поручениям — принято, начато, сдано, продлено — станут ещё одним признаком
жизни поручения рядом с контрольной отметкой, движением задачи и промежуточной информацией
(`app.domain.ijro.LifeSource`).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SetaEventKind(StrEnum):
    """Что SETA сообщает о поручении (ТЗ 11)."""

    ACCEPTED = "accepted"
    STARTED = "started"
    SUBMITTED = "submitted"
    EXTENDED = "extended"


@dataclass(frozen=True, slots=True)
class SetaEvent:
    """Событие по поручению. Поручение — по номеру из таблицы Ижро: другого общего ключа у
    двух систем нет."""

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
