"""Человекочитаемые номера записей: PRJ-2026-001, TSK-2026-00123.

По ним запись называют вслух и ищут в переписке; идентификатор для этого не годится.

Номер считается по числовому хвосту, а не по строке. На тысячном проекте года строковое
сравнение поставило бы «PRJ-2026-1000» раньше «PRJ-2026-999», номер начал бы повторяться,
а уникальность превратила бы это в отказ заводить новые записи — в декабре, без
объяснения.

Гонка двух одновременных созданий закрыта не блокировкой, а уникальностью столбца:
вносящих двое, столкновение практически невозможно, а уникальный индекс превращает его в
честную ошибку вместо двух записей с одним номером. Блокировка ради этого стоила бы
дороже, чем случай, который она предотвращает.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def next_code(
    session: AsyncSession,
    *,
    column: Any,
    prefix: str,
    digits: int,
    today: date,
) -> str:
    """Следующий свободный номер года для указанного столбца."""
    head = f"{prefix}-{today.year}-"

    last = await session.scalar(
        select(func.max(cast(func.substr(column, len(head) + 1), Integer))).where(
            column.like(f"{head}%")
        )
    )
    return f"{head}{(last or 0) + 1:0{digits}d}"
