"""Предпросмотр офисных форматов не строится.

Отказ немедленный, а не пустой PDF: файл без предпросмотра должен выглядеть как файл без
предпросмотра. Пустая страница вместо таблицы читается как «таблица пустая», и это хуже,
чем прямая надпись «предпросмотр недоступен».
"""

from __future__ import annotations

from app.adapters.preview import ConversionError


class NoConverter:
    """Ничего не преобразует."""

    name = "disabled"

    async def to_pdf(self, data: bytes, *, filename: str) -> bytes:
        raise ConversionError("построение предпросмотра выключено настройкой")
