"""Метка изменений — дешёвый ответ на «изменилось ли что-нибудь?» (ADR-0034).

Экран раз в 15 секунд спрашивает только метку, а данные разделов перечитывает, когда она
сменилась. Метка складывается из того, что меняет картину на экранах:

- **журнал изменений** — каждая правка данных пишется туда в той же транзакции
  (инвариант 5): его размер и время последней записи;
- **то, что живёт мимо журнала, но видно на экране**: привоз Ижро («по таблице от…»),
  прогоны задач (состояние системы), уведомления (дошла ли сводка), подписка на
  уведомления (устройство руководителя), отметки обхода.

Сессии и визиты в метку не входят: отметка визита меняется от самого опроса, и метка
менялась бы на каждый запрос, ничего не сэкономив. Размер журнала стоит рядом со временем
последней записи нарочно: две транзакции могут закончиться не в том порядке, в каком
начались, и время последней записи у второй будет старше, — а число записей вырастет всегда.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import AuditLog, IjroImport, JobRun, Notification, PushSubscription, RoundMark

Touched = type[IjroImport | JobRun | Notification | PushSubscription]


def _touched(model: Touched) -> ColumnElement[Any]:
    return func.max(func.coalesce(model.updated_at, model.created_at))


async def stamp(session: AsyncSession, *, day: str) -> str:
    """Метка — короткий отпечаток состояния: совпала — экран не перечитывает ничего.

    День по Ташкенту входит в метку: в полночь «горит» становится «просрочено» без единой
    правки, и экран должен перечитаться сам.
    """
    row = (
        await session.execute(
            select(
                select(func.count()).select_from(AuditLog).scalar_subquery(),
                select(func.max(AuditLog.occurred_at)).scalar_subquery(),
                select(_touched(IjroImport)).scalar_subquery(),
                select(_touched(JobRun)).scalar_subquery(),
                select(_touched(Notification)).scalar_subquery(),
                select(_touched(PushSubscription)).scalar_subquery(),
                select(func.count()).select_from(RoundMark).scalar_subquery(),
            )
        )
    ).one()
    raw = "|".join([day, *("" if value is None else str(value) for value in row)])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
