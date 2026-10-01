"""Таблица Word для тестов привоза — собирается в памяти.

Файлы `.docx` в репозиторий не попадают (`.gitignore`: настоящие таблицы — данные
агентства), поэтому образец строится кодом: та же разметка WordprocessingML, что у
«Назорат жадвали», — абзацы в ячейках, разделитель месяца одной ячейкой на всю ширину, —
и вымышленные номера и фамилии.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from xml.sax.saxutils import escape

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

HEADER = (
    "№",
    "Ҳужжат тури ва рақами",
    "Топшириқ мазмуни",
    "Ижро муддати",
    "Масъул ижрочи",
    "Ижро ҳолати",
    "Изоҳ",
)
"""Семь граф, как у настоящих таблиц (ADR-0025); названия — по смыслу граф."""

Cell = Sequence[str]
Row = Sequence[Cell] | str
"""Строка — ячейки-абзацы; строка-текст — разделитель месяца («СЕНТЯБРЬ»)."""


def _paragraph(text: str) -> str:
    return f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def _row(row: Row, width: int) -> str:
    if isinstance(row, str):
        return (
            f'<w:tr><w:tc><w:tcPr><w:gridSpan w:val="{width}"/></w:tcPr>'
            f"{_paragraph(row)}</w:tc></w:tr>"
        )
    cells = "".join(
        "<w:tc>" + ("".join(_paragraph(text) for text in cell) or "<w:p/>") + "</w:tc>"
        for cell in row
    )
    return f"<w:tr>{cells}</w:tr>"


def build(
    title: str, rows: Sequence[Row], *, header: Sequence[str] = HEADER, raw_xml: str | None = None
) -> bytes:
    """Файл `.docx` с заголовком и одной таблицей."""
    body = _paragraph(title) + "<w:tbl>"
    body += _row([[name] for name in header], len(header))
    body += "".join(_row(row, len(header)) for row in rows)
    body += "</w:tbl>"
    document = f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    xml = raw_xml or f'<?xml version="1.0" encoding="UTF-8"?>{document}'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def row(
    number: int,
    document: Sequence[str],
    content: Sequence[str],
    due: str,
    responsible: Sequence[str],
    state: str = "",
) -> list[list[str]]:
    return [
        [str(number)],
        list(document),
        list(content),
        [due],
        list(responsible),
        [state] if state else [],
        [],
    ]
