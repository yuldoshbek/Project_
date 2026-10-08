"""Чтение таблиц из `.docx` — на stdlib, без `python-docx`.

`zipfile` + `xml.etree.ElementTree`: решение плана ввоза «Ижро» (ORB-104), и причина та же.
`python-docx` не даёт двух нужных вещей — границ абзацев внутри ячейки и числа ячеек в
строке с учётом `gridSpan`, — и за ними всё равно пришлось бы спускаться к XML. Плюс ни
одной зависимости в развёртывании (LIMITS, Л5).

Что возвращается — только структура: абзацы до таблиц (там заголовок с годом) и таблицы
как строки ячеек, ячейка — **список абзацев, а не склейка**. Иначе «PA 1/1-484» и
«27.01.2026» из соседних абзацев слипаются в «PA 1/1-48427.01.2026». Смысл ячеек
разбирает `app.domain.ijro_import`.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

from app.domain.errors import RuleViolationError

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

MAX_SIZE = 10 * 1024 * 1024
"""Самая большая таблица заказчика — 115 строк, около 200 КБ. Десять мегабайт — запас
вдесятеро на вставленные картинки, а не приглашение грузить что угодно."""

MAX_XML_SIZE = 50 * 1024 * 1024
"""Предел распакованного `document.xml`: архив в мегабайт может развернуться в гигабайты
(«zip-бомба»), и проверять надо размер после распаковки, а не файла."""


@dataclass(frozen=True, slots=True)
class Row:
    cells: tuple[tuple[str, ...], ...]
    """Ячейки по порядку; ячейка — абзацы без пустых."""

    @property
    def width(self) -> int:
        return len(self.cells)


@dataclass(frozen=True, slots=True)
class Document:
    paragraphs: tuple[str, ...]
    """Абзацы вне таблиц до первой таблицы: заголовок «… Назорат жадвали 2026 йил»."""

    tables: tuple[tuple[Row, ...], ...]


def _paragraph_text(paragraph: ElementTree.Element) -> list[str]:
    """Текст абзаца; разрыв строки (`w:br`) делит абзац надвое — для разбора это граница."""
    parts: list[str] = [""]
    for node in paragraph.iter():
        if node.tag == f"{_W}t" and node.text:
            parts[-1] += node.text
        elif node.tag == f"{_W}tab":
            parts[-1] += " "
        elif node.tag in {f"{_W}br", f"{_W}cr"}:
            parts.append("")
    return [part.strip() for part in parts if part.strip()]


def _cell(cell: ElementTree.Element) -> tuple[str, ...]:
    texts: list[str] = []
    for paragraph in cell.iter(f"{_W}p"):
        texts += _paragraph_text(paragraph)
    return tuple(texts)


def _table(table: ElementTree.Element) -> tuple[Row, ...]:
    rows: list[Row] = []
    for row in table.findall(f"{_W}tr"):
        cells: list[tuple[str, ...]] = []
        for cell in row.findall(f"{_W}tc"):
            properties = cell.find(f"{_W}tcPr")
            merge = properties.find(f"{_W}vMerge") if properties is not None else None
            # Продолжение объединённой по вертикали ячейки — пустое место под первой её
            # частью: текста в нём нет, и считать его ячейкой со своим значением нельзя.
            if merge is not None and merge.get(f"{_W}val") in (None, "continue"):
                cells.append(())
                continue
            cells.append(_cell(cell))
        rows.append(Row(cells=tuple(cells)))
    return tuple(rows)


def read(content: bytes) -> Document:
    """Таблицы и заголовок из файла Word. Не `.docx` — понятный отказ, а не трассировка."""
    if len(content) > MAX_SIZE:
        raise RuleViolationError("Файл больше 10 МБ — это не контрольная таблица")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if archive.getinfo("word/document.xml").file_size > MAX_XML_SIZE:
                raise RuleViolationError("Таблица в файле слишком велика для разбора")
            xml = archive.read("word/document.xml")
        # Атаки сущностями XML («billion laughs», внешние сущности) идут через DOCTYPE, а
        # в настоящем `document.xml` его не бывает никогда: такой файл — не таблица Word.
        # Это закрывает их без `defusedxml` — ещё одной зависимости ради одной проверки.
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
            raise RuleViolationError("Файл не похож на таблицу Word (.docx)")
        root = ElementTree.fromstring(xml)  # noqa: S314 — DOCTYPE отвергнут выше
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise RuleViolationError(
            "Файл не похож на таблицу Word (.docx)",
            detail="Сохраните таблицу в Word как «Документ Word (.docx)» и загрузите снова",
        ) from error

    body = root.find(f"{_W}body")
    if body is None:
        raise RuleViolationError("В файле Word нет содержимого")
    paragraphs: list[str] = []
    tables: list[tuple[Row, ...]] = []
    for node in body:
        if node.tag == f"{_W}tbl":
            tables.append(_table(node))
        elif node.tag == f"{_W}p" and not tables:
            paragraphs += _paragraph_text(node)
    return Document(paragraphs=tuple(paragraphs), tables=tuple(tables))
